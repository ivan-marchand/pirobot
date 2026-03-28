import React from 'react';
import IconButton from '@mui/material/IconButton';
import Box from '@mui/material/Box';
import Tooltip from "@mui/material/Tooltip";
import { Link } from 'react-router-dom'
import HomeIcon from '@mui/icons-material/Home';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import SaveIcon from '@mui/icons-material/Save';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';

class Settings extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            robot_config: {},
            form_values: {}
        }
        this.ws = null
    }

    componentDidMount() {
        this.connect();
    }
    timeout = 250; // Initial timeout duration as a class variable

    /**
     * @function connect
     * This function establishes the connect with the websocket and also ensures constant reconnection if connection closes
     */
    connect = (onopen_callback) => {
        console.log("Connecting to robot websocket");
        let ws_url = "ws://" + (window.location.port === "3000" ? "localhost:8080" : window.location.host) + "/ws/robot";

        var ws = new WebSocket(ws_url);
        let that = this; // cache the this
        var connectInterval;

        // websocket onopen event listener
        ws.onopen = () => {
            console.log("Connected to robot websocket");

            this.ws = ws;
            this.get_robot_config()
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
            } else if (message.topic === "configuration") {
                this.updateConfiguration(message.message)
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
        console.log(status.status)
    }

    updateConfiguration = (configuration) => {
        console.log("Config", configuration)
        let robot_config = {}
        for (let config_name in configuration.config) {
            if (!robot_config.hasOwnProperty(configuration.config[config_name].category)) {
                robot_config[configuration.config[config_name].category] = {}
            }
            robot_config[configuration.config[config_name].category][config_name] = configuration.config[config_name]
        }
        this.setState({robot_config: robot_config, form_values: {}})
    }

    send_action = (type, action, args={}) => {
        this.send_json({topic: "robot", message: {type: type, action: action, args: args}});
    }

    send_json = (json_data) => {
        this.ws.send(
            JSON.stringify(json_data)
        );
    }

    get_robot_config = () => {
        this.send_action("configuration", "get");
    }

    update_form_value = (config_name, e) => {
        let form_values = this.state.form_values
        form_values[config_name] = e.target.value
        this.setState({form_values: form_values})
    }

    get_robot_config_input = (config_name, config) => {
        let value = config.value;
        if (this.state.form_values.hasOwnProperty(config_name)) {
            value = this.state.form_values[config_name]
        }
        if (config.type === "bool") {
            return (
                <Select value={value} variant="standard" size="small" onChange={this.update_form_value.bind(this, config_name)}>
                    <MenuItem value={true}>Yes</MenuItem>
                    <MenuItem value={false}>No</MenuItem>
                </Select>
           )
        } else if (config.type === "str" && config.hasOwnProperty("choices")) {
            return (
                <Select value={value} variant="standard" size="small" onChange={this.update_form_value.bind(this, config_name)}>
                {Object.keys(config.choices).map((index) => (
                    <MenuItem value={config.choices[index]}>{config.choices[index]}</MenuItem>
                ))}
                </Select>
           )
        } else {
            return (
                <TextField sx={{width: 150}} value={value} variant="standard" size="small" onChange={this.update_form_value.bind(this, config_name)}/>
            )
        }
    }

    update_robot_config = (config_name) => {
        if (this.state.form_values.hasOwnProperty(config_name)) {
            let value = this.state.form_values[config_name]
            this.send_json({topic: "robot", message: {type: "configuration", action: "update", args: {key: config_name, value: value}}});
        }
    }

    reset_robot_config = (config_name) => {
        this.send_json({topic: "robot", message: {type: "configuration", action: "delete", args: {key: config_name}}});
    }

    display_robot_config(category) {
        if (category !== "debug") {
            return [
                <TableHead>
                  <TableRow>
                    <TableCell colSpan={4} align="center" sx={{'font-weight': 'bold', 'font-size': '20px' }}>{category.toUpperCase()}</TableCell>
                  </TableRow>
                </TableHead>,
                <TableHead>
                  <TableRow>
                    <TableCell sx={{'font-weight': 'bold', 'font-size': '20px' }}>Name</TableCell>
                    <TableCell sx={{'font-weight': 'bold', 'font-size': '20px' }} align="right">Type</TableCell>
                    <TableCell sx={{'font-weight': 'bold', 'font-size': '20px' }}>Value</TableCell>
                    <TableCell></TableCell>
                  </TableRow>
                </TableHead>,
                <TableBody>
                  {Object.keys(this.state.robot_config[category]).map((config_name) => (
                    <TableRow
                      key={config_name}
                      sx={{ '&:last-child td, &:last-child th': { border: 0 } }}
                    >
                      <TableCell sx={{'font-size': '20px'}} component="th" scope="config_name">
                        {config_name}
                      </TableCell>
                      <TableCell sx={{'font-size': '20px'}} align="right">{this.state.robot_config[category][config_name].type}</TableCell>
                      <TableCell sx={{'font-size': '20px'}} align="left">{this.get_robot_config_input(config_name, this.state.robot_config[category][config_name])}</TableCell>
                      <TableCell sx={{'font-size': '20px'}} align="right">
                          <Tooltip title="Update"><IconButton size="small" onClick={this.update_robot_config.bind(this, config_name)}><SaveIcon/></IconButton></Tooltip>
                          <Tooltip title={'Reset (' + this.state.robot_config[category][config_name].default + ')'} onClick={this.reset_robot_config.bind(this, config_name)}><IconButton size="small"><RestartAltIcon/></IconButton></Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
            ]
        }
    }

    render() {
        document.body.style.overflow = "";
        return (
            <div className="App ">
                <Box sx={{display: 'flex', width: 'fit-content', bgcolor: 'grey', margin: 1, border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1}}>
                    <Tooltip title="Home"><IconButton component={Link} to="/" ><HomeIcon/></IconButton></Tooltip>
                </Box>
                <p>Robot Settings</p>
                <TableContainer sx={{display: 'flex', width: 'fit-content', bgcolor: 'grey', margin: 1, border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1}}>
                  <Table size='small' aria-label="simple table">
                    {Object.keys(this.state.robot_config).map((category) => (
                        this.display_robot_config(category)
                      ))}
                  </Table>
                </TableContainer>
             </div>
        );
    }
}

export default Settings;