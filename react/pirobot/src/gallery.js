import React from 'react';
import ImageList from '@mui/material/ImageList';
import ImageListItem from '@mui/material/ImageListItem';
import ImageListItemBar from '@mui/material/ImageListItemBar';
import IconButton from '@mui/material/IconButton';
import DownloadIcon from '@mui/icons-material/Download';
import Box from '@mui/material/Box';
import Tooltip from "@mui/material/Tooltip";
import { Link } from 'react-router-dom'
import HomeIcon from '@mui/icons-material/Home';

class Gallery extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            medias: [],
            nb_col: 2
        }
    }

    componentDidMount() {
        let url_prefix = window.location.port === "3000" ? "http://localhost:8080" : "";
        let url = url_prefix + (this.props.type === "video" ? '/api/v1/videos' : '/api/v1/pictures')
        fetch(url)
            .then(response => response.json())
            .then(data => {
                let nb_col = 2;
                if (data.length > 9) {
                    nb_col = 4;
                } else if (data.length > 4) {
                    nb_col = 3;
                }
                this.setState({medias: data, nb_col: nb_col})
            })
            .catch((error) => {
                console.error('Error:', error);
            });
    }

    get_picture_page = () => {
        let url_prefix = window.location.port === "3000" ? "http://localhost:8080" : "";
        let url = url_prefix + (this.props.type === "video" ? '/gallery/video' : '/gallery/picture')
        let image_width = Math.round(window.innerWidth / this.state.nb_col)
        return (
            <ImageList cols={this.state.nb_col} margin={20}>
              {this.state.medias.map((media) => (
                <ImageListItem key={media.filename}>
                  <img
                    srcSet={`${url}/${media.filename}?w=${image_width}`}
                    src={`${url}/${media.filename}?w=${image_width}`}
                    alt={media.filename}
                    fit="true"
                    loading="lazy"
                  />
                  <ImageListItemBar
                    title={`${media.robot_name} ${media.source} ${media.date} ${media.time}`}
                    position="top"
                    actionIcon={
                      <IconButton
                        sx={{ color: 'rgba(255, 255, 255, 0.54)' }}
                        aria-label={`info about ${media.filename}`}
                        component="a" href={`${url}/${media.filename}?full=y`} download
                      >
                       <DownloadIcon/>
                      </IconButton>
                    }
                  />
              </ImageListItem>
              ))}
            </ImageList>
        )
    }

    render() {
        document.body.style.overflow = "";
        return (
            <div className="App">
                <Box sx={{display: 'flex', width: 'fit-content', bgcolor: 'grey', margin: 1, border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1}}>
                    <Tooltip title="Home"><IconButton component={Link} to="/" ><HomeIcon/></IconButton></Tooltip>
                </Box>
                <p>{(this.props.type === "video" ? "Video" : "Photo")} Gallery</p>
                    {this.get_picture_page()}
            </div>
        );
    }
}

export default Gallery;
