import Grid from "@mui/material/Grid";
import IconButton from '@mui/material/IconButton';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import DangerousIcon from '@mui/icons-material/Dangerous'
import NorthWestIcon from '@mui/icons-material/NorthWest'
import NorthEastIcon from '@mui/icons-material/NorthEast'
import SouthWestIcon from '@mui/icons-material/SouthWest'
import SouthEastIcon from '@mui/icons-material/SouthEast'
import React from 'react';



class DirectionCross extends React.Component {

    button = (props) => {
        return (
            <IconButton
             onMouseUp={this.props.stop}
             onTouchEnd={this.props.stop}
             onMouseDown={this.props.move.bind(null, props.left_speed, props.right_speed)}
             onTouchStart={this.props.move.bind(null, props.left_speed, props.right_speed)}
             sx={{ bgcolor: 'grey' }}
             >
                {props.children}
             </IconButton>
        )
    }

    render() {
        return (
          <Grid container direction="column" spacing={2}>
            <Grid container item xs={4} spacing={2}>
                <Grid item xs={4}>
                  <this.button left_speed={0} right_speed={100}><NorthWestIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={100} right_speed={100}><ArrowUpwardIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={100} right_speed={0}><NorthEastIcon/></this.button>
                </Grid>
            </Grid>

            <Grid container item xs={4} spacing={2}>
                <Grid item xs={4}>
                  <this.button left_speed={-100} right_speed={100}><ArrowBackIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={0} right_speed={0}><DangerousIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={100} right_speed={-100}><ArrowForwardIcon/></this.button>
                </Grid>
            </Grid>

            <Grid container item xs={4} spacing={2}>
                <Grid item xs={4}>
                  <this.button left_speed={-100} right_speed={0}><SouthWestIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={-100} right_speed={-100}><ArrowDownwardIcon/></this.button>
                </Grid>
                <Grid item xs={4}>
                  <this.button left_speed={0} right_speed={-100}><SouthEastIcon/></this.button>
                </Grid>
            </Grid>
          </Grid>
          )
    }
}

export default DirectionCross;
