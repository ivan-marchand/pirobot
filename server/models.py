import configparser
import json
import logging
import os

from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from logger import RobotLogger

logger = logging.getLogger(__name__)

Base = declarative_base()

DEFAULT_CONFIG = {
    "robot_config": "pirobot",
    "log_file": None,
    "message_log_file": None,
    "log_level": "INFO",
    "video_server_port": 8001,
    "server_port": 8000,
    "webserver_port": 8080,
}


# Create your models here.
class Config(Base):
    CONFIG_KEYS = None
    USER_CONFIG_DIR = os.path.join(os.environ["HOME"], ".pirobot")
    db_engine = None
    db_session = None
    user_config = None

    __tablename__ = 'server_config'

    key = Column(String(30), primary_key=True)
    value = Column(String(2048), nullable=False)

    @staticmethod
    def _convert_to_type(value, config_type):
        if config_type == "int":
            return int(value)
        elif config_type == "str":
            return str(value)
        elif config_type == "float":
            return float(value)
        elif config_type == "bool":
            if type(value) == str:
                return value.lower() in ('y', 'true')
            else:
                return bool(value)
        elif config_type == json:
            return json.loads(value)
        else:
            return value

    @staticmethod
    def setup(robot_config):
        if not os.path.isdir(Config.USER_CONFIG_DIR):
            os.makedirs(Config.USER_CONFIG_DIR)

        Config.user_config = configparser.ConfigParser(defaults=DEFAULT_CONFIG, default_section="pirobot", allow_no_value=True)
        Config.user_config.read(["/etc/pirobot/pirobot.config", os.path.join(Config.USER_CONFIG_DIR, "pirobot.config")])

        # Setup logger
        RobotLogger.setup_logger(
            app_log_file=Config.user_config.get("pirobot", "log_file"),
            message_log_file=Config.user_config.get("pirobot", "message_log_file"),
            level=Config.user_config.get("pirobot", "log_level")
        )
        if robot_config is None:
            robot_config = Config.user_config.get("pirobot", "robot_config")

        logger.info(f"Starting robot with config {robot_config}")

        config_file_dir = os.path.join(os.path.dirname(__file__), "config")
        if not os.path.isdir(config_file_dir):
            config_file_dir = "/etc/pirobot/config"
        config_file_path = os.path.join(config_file_dir, f"{robot_config}.robot.json")
        if os.path.isfile(robot_config):
            config_file_path = robot_config
        elif not os.path.isfile(config_file_path):
            logger.warning(f"Warning: Invalid config file {robot_config}, using default instead")
            config_file_path = os.path.join(config_file_dir, "pirobot.robot.json")
        with open(config_file_path) as config_file:
            Config.CONFIG_KEYS = Config.load_config_file(config_file_dir, config_file)

        db_file_path = os.path.join(Config.USER_CONFIG_DIR, "db.sqlite3")
        Config.db_engine = create_engine(f"sqlite:///{db_file_path}")

        if not os.path.isfile(db_file_path):
            Base.metadata.create_all(Config.db_engine)

        Config.session_maker = sessionmaker(bind=Config.db_engine)

    @staticmethod
    def merge_config(left_config, right_config):
        merged_config = {}
        for config_name in left_config.keys():
            merged_config[config_name] = left_config[config_name]
            merged_config[config_name].update(right_config.get(config_name, {}))
        return merged_config

    @staticmethod
    def load_config_file(config_file_dir, config_file):
        robot_config = json.load(config_file)
        if "include" in robot_config:
            with open(os.path.join(config_file_dir, robot_config["include"])) as include_config_file:
                robot_config = Config.merge_config(
                    json.load(include_config_file)["config"], robot_config.get("config", {})
                )
        return robot_config

    @staticmethod
    def get_session():
        if Config.db_engine is not None:
            if Config.db_session is None:
                Config.db_session = Config.session_maker()
            return Config.db_session
        else:
            logger.error("DB Engine not found, run setup() first")

    @staticmethod
    def get(key):
        config = Config.CONFIG_KEYS.get(key)
        if config is None:
            raise KeyError(key)
        else:
            session = Config.get_session()
            c = Config.get_from_db(session, key)
            if c is not None:
                return Config._convert_to_type(c.value, config.get("type"))
        return config.get("default")

    @staticmethod
    def get_video_server_port():
        return int(Config.user_config.get("pirobot", "video_server_port"))

    @staticmethod
    def get_webserver_port():
        return int(Config.user_config.get("pirobot", "webserver_port"))

    @staticmethod
    def get_server_port():
        return int(Config.user_config.get("pirobot", "server_port"))

    @staticmethod
    def get_from_db(session, key):
        for c in session.query(Config).filter(Config.key == key):
            return c
        return None

    @staticmethod
    def save(key, value):
        if Config.is_valid(key, value):
            session = Config.get_session()
            c = Config.get_from_db(session, key)
            if c is not None:
                c.value = str(value)
            else:
                c = Config(key=key, value=str(value))

            session.add(c)
            session.commit()
            return True
        else:
            print(key, value)
            return False

    @staticmethod
    def delete(key):
        session = Config.get_session()
        c = Config.get_from_db(session, key)
        if c is not None:
            session.delete(c)
            session.commit()
            return True

        return False

    @staticmethod
    def need_setup(key):
        if key in Config.CONFIG_KEYS:
            need_setup = Config.CONFIG_KEYS[key].get("need_setup", [])
            if type(need_setup) == str:
                return [need_setup]
            else:
                return need_setup
        return []

    @staticmethod
    def is_valid(key, value):
        config = Config.CONFIG_KEYS.get(key)
        if config is not None:
            try:
                Config._convert_to_type(value, config.get("type"))
                return True
            except:
                logger.error(f"Unable to parse value as {config.get('type')}", exc_info=True)
                return False
        else:
            logger.error(f"Unknown key {key}")
            return False

    @staticmethod
    def get_config():
        config = {}
        for key, key_config in Config.CONFIG_KEYS.items():
            config[key] = key_config.copy()
            config[key]["value"] = Config.get(key)
        return config

    @staticmethod
    def export_config():
        config = {}
        for key, key_config in Config.CONFIG_KEYS.items():
            if key_config.get('export', False):
                config[key] = Config.get(key)
        return config

    @staticmethod
    async def process(message, protocol):
        success = False
        need_setup = False
        if message["action"] == "get":
            success = True
            await protocol.send_message(
                "configuration",
                {
                    "type": "configuration",
                    "action": "get",
                    "config": Config.get_config(),
                    "success": success,
                }
            )
        elif message["action"] == "update":
            success = Config.save(message["args"]["key"], message["args"]["value"])
            need_setup = Config.need_setup(message["args"]["key"])
            await protocol.send_message(
                "configuration",
                {
                    "type": "configuration",
                    "action": "update",
                    "config": Config.get_config(),
                    "success": success,
                }
            )
        elif message["action"] == "delete":
            success = Config.delete(message["args"]["key"])
            need_setup = Config.need_setup(message["args"]["key"])
            await protocol.send_message(
                "configuration",
                {
                    "type": "configuration",
                    "action": "delete",
                    "config": Config.get_config(),
                    "success": success,
                }
            )
        return success, need_setup
