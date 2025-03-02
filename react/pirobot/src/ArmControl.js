import Divider from '@mui/material/Divider';
import Grid from "@mui/material/Grid";
import Stack from '@mui/material/Stack';
import Slider from "@mui/material/Slider";
import React from 'react';



class ArmControl extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            shoulder_slider_position: 0,
            wrist_slider_position: 0,
            forearm_slider_position: 0,
            lock_wrist: false
        };
    }

    move_arm = (servo, e) => {
        var s = {}
        s[servo + "_slider_position"] = e.target.value
        this.props.move(servo, e.target.value, this.state.lock_wrist)
        this.setState(s)
    }

    stop_arm = (servo, e) => {
        var s = {}
        s[servo + "_slider_position"] = 0
        this.props.stop()
        this.setState(s)
    }

    move_arm_limb = (servo, e) => {
        this.props.move_limb(servo, e)
    }

    relative_slider = (props) => {
        return (
            <Slider
                min={-100}
                max={100}
                step={1}
                aria-label={props["aria-label"]}
                orientation="horizontal"
                style={{width: 150}}
                value={this.state[props.servo + "_slider_position"]}
                onChange={this.move_arm.bind(this, props.servo)}
                onChangeCommitted={this.stop_arm.bind(this, props.servo)}
                marks={[{value: 0}]}
            />
        )
    }

    absolute_slider = (props) => {
        return (
            <Slider
                color="success"
                min={0}
                max={this.props.status.config[props.servo].max_angle}
                step={1}
                aria-label={props["aria-label"]}
                orientation="horizontal"
                valueLabelDisplay="auto"
                style={{width: 150}}
                value={this.props.status.position[props.servo]}
                onChange={this.move_arm_limb.bind(this, props.servo)}
                marks={[{value: 0}]}
            />
        )
    }

    render() {
        if (this.props.enabled) {
            return (
              <Grid container direction="column" spacing={0}>
                <Stack
                    spacing={0}
                    justifyContent="center"
                    alignItems="center"
                    direction="column">
                    <this.absolute_slider servo="shoulder"/>
                    <this.relative_slider servo="shoulder"/>
                    <Divider orientation="horizontal" flexItem />
                    <this.absolute_slider servo="forearm"/>
                    <this.relative_slider servo="forearm"/>
                    <Divider orientation="horizontal" flexItem />
                    <this.absolute_slider servo="wrist"/>
                    <this.relative_slider servo="wrist"/>
                    <Divider orientation="horizontal" flexItem />
                    <this.absolute_slider servo="claw"/>
                </Stack>
              </Grid>
              )
          }
    }
}

export default ArmControl;
