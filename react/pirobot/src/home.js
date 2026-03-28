import React from 'react';
import Box from '@mui/material/Box';
import Collapse from '@mui/material/Collapse';
import Divider from '@mui/material/Divider';
import Grid from "@mui/material/Grid";
import Slider from "@mui/material/Slider";
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CameraAltIcon from "@mui/icons-material/CameraAlt";
import DangerousIcon from '@mui/icons-material/Dangerous';
import FaceIcon from '@mui/icons-material/Face';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import PhotoLibraryIcon from '@mui/icons-material/PhotoLibrary';
import VideoLibraryIcon from '@mui/icons-material/VideoLibrary';
import StopIcon from '@mui/icons-material/Stop';
import IconButton from "@mui/material/IconButton";
import FaceRetouchingOffIcon from '@mui/icons-material/FaceRetouchingOff';
import SettingsIcon from '@mui/icons-material/Settings';
import Tooltip from "@mui/material/Tooltip";
import PictureInPictureIcon from '@mui/icons-material/PictureInPicture';
import SwitchCameraIcon from '@mui/icons-material/SwitchCamera';
import VerticalAlignCenterIcon from '@mui/icons-material/VerticalAlignCenter';
import RadarIcon from '@mui/icons-material/Radar';
import GamepadIcon from '@mui/icons-material/Gamepad';
import ControlCameraIcon from '@mui/icons-material/ControlCamera';
import FlashlightOnIcon from '@mui/icons-material/FlashlightOn';
import FlashlightOffIcon from '@mui/icons-material/FlashlightOff';
import PrecisionManufacturingIcon from '@mui/icons-material/PrecisionManufacturing';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import {Joystick} from "react-joystick-component";
import { Link } from 'react-router-dom'

import ArmControl from "./ArmControl"
import DirectionCross from "./DirectionCross"
import VideoStreamControl from "./VideoStreamControl";
import ResponsiveJoystick from './ResponsiveJoystick';


class Home extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            ws: null,
            fps: 0,
            robot_config: {},
            robot_name: null,
            robot_status: {},
            control: "joystick",
            control_arm: false,
            drive_slow_mode: false,
            overflowOpen: false,
        };
        this.selected_camera = "front"
    }


    componentDidMount() {
        this.connect();
    }
    timeout = 250; // Initial timeout duration as a class variable

    /**
     * @function connect
     * This function establishes the connect with the websocket and also ensures constant reconnection if connection closes
     */
    connect = () => {
        console.log("Connecting to robot websocket");
        let ws_url = "ws://" + (window.location.port === "3000" ? "localhost:8080" : window.location.host) + "/ws/robot";

        var ws = new WebSocket(ws_url);
        let that = this; // cache the this
        var connectInterval;

        // websocket onopen event listener
        ws.onopen = () => {
            console.log("Connected to robot websocket");

            this.setState({ ws: ws });

            that.timeout = 250; // reset timer to 250 on open of websocket connection
            clearTimeout(connectInterval); // clear Interval on on open of websocket connection
        };

        // websocket onclose event listener
        ws.onclose = e => {
            console.log(
                `Socket is closed. Reconnect will be attempted in ${Math.min(
                    10000 / 1000,
                    (that.timeout + that.timeout) / 1000
                )} second.`,
                e.reason
            );

            that.timeout = that.timeout + that.timeout; //increment retry interval
            connectInterval = setTimeout(this.check, Math.min(10000, that.timeout)); //call check function after timeout
        };

        ws.onmessage = evt => {
            // listen to data sent from the websocket server
            var message = JSON.parse(evt.data);
            if (message.topic === "status") {
                this.updateStatus(message.message)
            } else {
                console.log("Unknown message topic " + message.topic)
            }
        }

        // websocket onerror event listener
        ws.onerror = err => {
            console.error(
                "Socket encountered error: ",
                err.message,
                "Closing socket"
            );

            ws.close();
        };
    };

    /**
     * utilited by the @function connect to check if the connection is close, if so attempts to reconnect
     */
    check = () => {
        const { ws } = this.state;
        if (!ws || ws.readyState === WebSocket.CLOSED) this.connect(); //check if websocket instance is closed, if so call `connect` function.
    };

    updateStatus = (status) => {
        console.log(status)
        this.setState({robot_config: status.config, robot_name: status.robot_name, robot_status: status.status});
        document.title = status.robot_name
    }

    send_action = (type, action, args={}) => {
        this.send_json({topic: "robot", message: {type: type, action: action, args: args}});
    }

    send_json = (json_data) => {
        this.state.ws.send(
            JSON.stringify(json_data)
        );
    }

    handleJoystickMove = (e) => {
        let x_pos = e.x * 100;
        let y_pos = -e.y * 100;
        if (Math.abs(x_pos) < 2 && Math.abs(y_pos) < 2) {
            console.log("Force stop!")
            this.send_action("drive", "stop")
        }
        else {

            let right_speed = Math.min(Math.max(-y_pos - x_pos, -100), 100)
            let left_speed = Math.min(Math.max(-y_pos + x_pos, -100), 100)
            this.handleMoveRobot(left_speed, right_speed)
        }
    }

    handleMoveRobot = (left_speed, right_speed) => {
        if (this.state.drive_slow_mode) {
            right_speed = Math.round(0.3 * right_speed)
            left_speed = Math.round(0.3 * left_speed)
        }

        let left_orientation = 'F';
        if (left_speed < 0) {
            left_orientation = 'B'
        }

        let right_orientation = 'F'
        if (right_speed < 0) {
            right_orientation = 'B'
        }

        this.send_action(
            "drive",
            "move",
            {
                left_orientation: left_orientation,
                left_speed: Math.abs(left_speed),
                right_orientation: right_orientation,
                right_speed: Math.abs(right_speed),
                duration: 30,
                distance: null,
                rotation: null,
                auto_stop: false,
            }
         );
    }

    handleStopRobot = (e) => {
        this.send_action("drive", "stop");
    }

    set_camera_position = (e) => {
        this.send_action("camera", "set_position", {"position": e.target.value});
    }

    center_camera_position = (e) => {
        this.send_action("camera", "center_position");
    }

    move_arm_to_position = (position_id) => {
        this.send_action("arm", "move_to_position", {"position_id": position_id});
    }

    move_arm_limb = (servo, e) => {
        this.send_action("arm", "move_servo_to_position", {"id": servo, "angle": e.target.value});
    }

    move_arm = (servo, speed, lock_wrist) => {
        this.send_action("arm", "move", {"id": servo, "speed": speed, "lock_wrist": lock_wrist});
    }

    stop_arm = () => {
        this.send_action("arm", "stop", {});
    }

    updateFps = (fps) => {
        this.setState({fps: fps})
    }

    toogleCamera = () => {
        this.selected_camera = this.selected_camera === "front" ? "back" : "front"
        this.send_action("camera", "select_camera", {"camera": this.selected_camera})
    }

    toggleControl = () => {
        this.setState({control: this.state.control === "joystick" ? "cross" : "joystick"});
    }

    toggleArmControl = () => {
        this.setState({control_arm: !this.state.control_arm});
    }

    render() {
        document.body.style.overflow = "hidden";
        return (
            <Box sx={{
  position: { xs: 'fixed', md: 'static' },
  top: { xs: 0 }, left: { xs: 0 }, right: { xs: 0 }, bottom: { xs: 0 },
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}}>
                {/* ── DESKTOP: toolbar (hidden on mobile) ── */}
                <Box sx={{ display: { xs: 'none', md: 'flex' }, flexWrap: 'wrap', width: 'fit-content',
                    bgcolor: 'grey', border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
                  <Tooltip title="Open photo gallery"><IconButton component={Link} to="/pictures"><PhotoLibraryIcon/></IconButton></Tooltip>
                  <Tooltip title="Open video gallery"><IconButton component={Link} to="/videos"><VideoLibraryIcon/></IconButton></Tooltip>
                  <Tooltip title="Robot Settings"><IconButton component={Link} to="/settings"><SettingsIcon/></IconButton></Tooltip>
                  <Divider orientation="vertical" flexItem/>
                  {this.state.robot_config.robot_has_back_camera && <IconButton onClick={this.toogleCamera}><SwitchCameraIcon/></IconButton>}
                  {this.state.robot_config.robot_has_back_camera && <IconButton onClick={this.send_action.bind(this, "camera", "toggle_overlay", {})}><PictureInPictureIcon/></IconButton>}
                  <Tooltip title="Record a Video"><IconButton onClick={this.send_action.bind(this, "camera", "start_video", {})}><FiberManualRecordIcon/></IconButton></Tooltip>
                  <Tooltip title="Stop Video Recording"><IconButton onClick={this.send_action.bind(this, "camera", "stop_video", {})}><StopIcon/></IconButton></Tooltip>
                  <Tooltip title="Take a Photo"><IconButton onClick={this.send_action.bind(this, "camera", "capture_picture", {})}><CameraAltIcon/></IconButton></Tooltip>
                  <Divider orientation="vertical" flexItem/>
                  {this.state.control === "joystick" && <Tooltip title="Use D-pad"><IconButton onClick={this.toggleControl}><GamepadIcon/></IconButton></Tooltip>}
                  {this.state.control === "cross"   && <Tooltip title="Use Joystick"><IconButton onClick={this.toggleControl}><ControlCameraIcon/></IconButton></Tooltip>}
                  {this.state.robot_config.robot_has_arm && <Tooltip title="Toggle Arm Control"><IconButton onClick={this.toggleArmControl}><PrecisionManufacturingIcon/></IconButton></Tooltip>}
                  <Divider orientation="vertical" flexItem/>
                  {this.state.robot_config.robot_has_light && <Tooltip title="Front Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle", {})}>{this.state.robot_status.light?.left_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
                  {this.state.robot_config.robot_has_light && this.state.robot_config.robot_has_arm && <Tooltip title="Arm Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle_arm_light", {})}>{this.state.robot_status.light?.arm_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
                  {this.state.robot_config.robot_has_light && <Divider orientation="vertical" flexItem/>}
                  <Tooltip title="Face Recognition"><IconButton onClick={this.send_action.bind(this, "face_detection", "toggle", {})}>{this.face_detection ? <FaceRetouchingOffIcon/> : <FaceIcon/>}</IconButton></Tooltip>
                  <Tooltip title="Start Patrolling"><IconButton onClick={this.send_action.bind(this, "drive", "patrol", {})}><RadarIcon/></IconButton></Tooltip>
                  <Tooltip title="Stop Robot"><IconButton onClick={this.send_action.bind(this, "drive", "stop", {})}><DangerousIcon/></IconButton></Tooltip>
                </Box>

                {/* ── BODY ROW: fills remaining height, position:relative for mobile overlays ── */}
                <Box sx={{ flex: 1, display: 'flex', minHeight: 0, position: 'relative' }}>

                  {/* LEFT column: joystick/dpad/arm — desktop only */}
                  <Box sx={{ display: { xs: 'none', md: 'flex' }, width: '16.67%', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ display: (this.state.control === "joystick" && !this.state.control_arm) ? "block" : "none" }}>
                      <ResponsiveJoystick move={this.handleJoystickMove} stop={this.handleStopRobot} />
                    </div>
                    <div style={{ paddingLeft: 5, display: (this.state.control === "cross" && !this.state.control_arm) ? "block" : "none" }}>
                      <DirectionCross move={this.handleMoveRobot} stop={this.handleStopRobot} />
                    </div>
                    <div style={{ paddingLeft: 5, display: this.state.control_arm ? "block" : "none" }}>
                      <ArmControl
                        move={this.move_arm} stop={this.stop_arm} move_limb={this.move_arm_limb}
                        enabled={this.state.robot_config.robot_has_arm} status={this.state.robot_status.arm}
                      />
                    </div>
                  </Box>

                  {/* CENTER: video — always rendered, full width on mobile */}
                  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 0 }}>
                    <VideoStreamControl updateFps={this.updateFps} />
                  </Box>

                  {/* RIGHT column: camera servo slider — desktop only */}
                  <Box sx={{ display: { xs: 'none', md: 'flex' }, width: '16.67%', alignItems: 'center', justifyContent: 'center' }}>
                    {this.state.robot_config.robot_has_camera_servo && (
                      <Stack spacing={2} justifyContent="center" alignItems="center" direction="column">
                        <Slider
                          min={0} max={100} step={1}
                          style={{ height: 200 }}
                          aria-label="Camera position"
                          orientation="vertical"
                          valueLabelDisplay="auto"
                          value={this.state.robot_status.camera?.position}
                          onChange={this.set_camera_position}
                          marks={[{ value: this.state.robot_status.camera?.center_position }]}
                        />
                        <IconButton onClick={this.center_camera_position}><VerticalAlignCenterIcon/></IconButton>
                      </Stack>
                    )}
                  </Box>

                  {/* ── MOBILE OVERLAYS (position:absolute, hidden on desktop) ── */}

                  {/* Mobile: floating toolbar pill */}
                  <Box sx={{
                    display: { xs: 'flex', md: 'none' },
                    position: 'absolute', top: 8, left: 8, right: 8, zIndex: 10,
                    bgcolor: 'rgba(30,30,30,0.88)', borderRadius: '20px', px: 1, py: 0.5,
                    alignItems: 'center', gap: 0.5,
                  }}>
                    <Tooltip title="Stop Robot">
                      <IconButton onClick={this.send_action.bind(this, "drive", "stop", {})} sx={{ color: '#e53935' }}>
                        <DangerousIcon/>
                      </IconButton>
                    </Tooltip>
                    <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(255,255,255,0.15)' }}/>
                    <Tooltip title="Record a Video"><IconButton onClick={this.send_action.bind(this, "camera", "start_video", {})}><FiberManualRecordIcon/></IconButton></Tooltip>
                    <Tooltip title="Stop Recording"><IconButton onClick={this.send_action.bind(this, "camera", "stop_video", {})}><StopIcon/></IconButton></Tooltip>
                    <Tooltip title="Take a Photo"><IconButton onClick={this.send_action.bind(this, "camera", "capture_picture", {})}><CameraAltIcon/></IconButton></Tooltip>
                    <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(255,255,255,0.15)' }}/>
                    {this.state.control === "joystick" && <Tooltip title="Use D-pad"><IconButton onClick={this.toggleControl}><GamepadIcon/></IconButton></Tooltip>}
                    {this.state.control === "cross"   && <Tooltip title="Use Joystick"><IconButton onClick={this.toggleControl}><ControlCameraIcon/></IconButton></Tooltip>}
                    {this.state.robot_config.robot_has_arm && <Tooltip title="Toggle Arm Control"><IconButton onClick={this.toggleArmControl}><PrecisionManufacturingIcon/></IconButton></Tooltip>}
                    <Box sx={{ flex: 1 }}/>
                    <IconButton aria-label="More actions" onClick={() => this.setState({ overflowOpen: !this.state.overflowOpen })}>
                      <MoreHorizIcon/>
                    </IconButton>
                  </Box>

                  {/* Mobile: overflow menu (slides down from toolbar) */}
                  <Collapse in={this.state.overflowOpen} sx={{ display: { xs: 'block', md: 'none' }, position: 'absolute', top: 56, left: 8, right: 8, zIndex: 10 }}>
                    <Box sx={{ bgcolor: 'rgba(30,30,30,0.92)', borderRadius: 2, p: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      <Tooltip title="Open photo gallery"><IconButton component={Link} to="/pictures"><PhotoLibraryIcon/></IconButton></Tooltip>
                      <Tooltip title="Open video gallery"><IconButton component={Link} to="/videos"><VideoLibraryIcon/></IconButton></Tooltip>
                      <Tooltip title="Robot Settings"><IconButton component={Link} to="/settings"><SettingsIcon/></IconButton></Tooltip>
                      {this.state.robot_config.robot_has_back_camera && <Tooltip title="Switch Camera"><IconButton onClick={this.toogleCamera}><SwitchCameraIcon/></IconButton></Tooltip>}
                      {this.state.robot_config.robot_has_back_camera && <Tooltip title="Picture in Picture"><IconButton onClick={this.send_action.bind(this, "camera", "toggle_overlay", {})}><PictureInPictureIcon/></IconButton></Tooltip>}
                      {this.state.robot_config.robot_has_light && <Tooltip title="Front Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle", {})}>{this.state.robot_status.light?.left_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
                      {this.state.robot_config.robot_has_light && this.state.robot_config.robot_has_arm && <Tooltip title="Arm Lights"><IconButton onClick={this.send_action.bind(this, "light", "toggle_arm_light", {})}>{this.state.robot_status.light?.arm_on ? <FlashlightOffIcon/> : <FlashlightOnIcon/>}</IconButton></Tooltip>}
                      <Tooltip title="Face Recognition"><IconButton onClick={this.send_action.bind(this, "face_detection", "toggle", {})}>{this.face_detection ? <FaceRetouchingOffIcon/> : <FaceIcon/>}</IconButton></Tooltip>
                      <Tooltip title="Start Patrolling"><IconButton onClick={this.send_action.bind(this, "drive", "patrol", {})}><RadarIcon/></IconButton></Tooltip>
                    </Box>
                  </Collapse>

                  {/* Mobile: floating joystick/dpad/arm — bottom left */}
                  <Box sx={{ display: { xs: 'block', md: 'none' }, position: 'absolute', bottom: 16, left: 16, zIndex: 10 }}>
                    <div style={{ display: (this.state.control === "joystick" && !this.state.control_arm) ? "block" : "none" }}>
                      <ResponsiveJoystick move={this.handleJoystickMove} stop={this.handleStopRobot} />
                    </div>
                    <div style={{ display: (this.state.control === "cross" && !this.state.control_arm) ? "block" : "none" }}>
                      <DirectionCross move={this.handleMoveRobot} stop={this.handleStopRobot} />
                    </div>
                    <div style={{ display: this.state.control_arm ? "block" : "none" }}>
                      <ArmControl
                        move={this.move_arm} stop={this.stop_arm} move_limb={this.move_arm_limb}
                        enabled={this.state.robot_config.robot_has_arm} status={this.state.robot_status.arm}
                      />
                    </div>
                  </Box>

                  {/* Mobile: camera servo slider — right edge */}
                  {this.state.robot_config.robot_has_camera_servo && (
                    <Box sx={{ display: { xs: 'flex', md: 'none' }, position: 'absolute', right: 8, top: 56, bottom: 80, zIndex: 10, flexDirection: 'column', alignItems: 'center' }}>
                      <Slider
                        min={0} max={100} step={1}
                        sx={{ flex: 1 }}
                        aria-label="Camera position"
                        orientation="vertical"
                        valueLabelDisplay="auto"
                        value={this.state.robot_status.camera?.position}
                        onChange={this.set_camera_position}
                        marks={[{ value: this.state.robot_status.camera?.center_position }]}
                      />
                      <IconButton onClick={this.center_camera_position}><VerticalAlignCenterIcon/></IconButton>
                    </Box>
                  )}

                  {/* Mobile: FPS badge — bottom right */}
                  <Typography variant="caption" sx={{
                    display: { xs: 'block', md: 'none' },
                    position: 'absolute', bottom: 8, right: 8, zIndex: 10,
                    color: 'rgba(255,255,255,0.5)', bgcolor: 'rgba(0,0,0,0.5)', borderRadius: 1, px: 1,
                  }}>
                    {this.state.fps} FPS
                  </Typography>

                </Box>

                {/* ── STATUS BAR: desktop only ── */}
                <Box sx={{ display: { xs: 'none', md: 'block' } }}>
                  <p style={{ margin: 0, padding: 0, fontSize: '15px' }}>
                    Connected to {this.state.robot_name} - {this.state.fps} FPS
                  </p>
                </Box>
            </Box>
        );
    }
}

export default Home;
