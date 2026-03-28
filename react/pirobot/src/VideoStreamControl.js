import React from "react";

const FPS_UPDATE_INTERVAL = 1;

class VideoStreamControl extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            frame: null,
        };
        this.ws = null
        this.frame_counter = 0
        this.last_frame_ts = 0
        this.slow_mode = false
    }

    start_streaming = (ws) => {
        console.log("Start streaming")
        ws.send("start")
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
        console.log("Connecting to video websocket");
        let ws_url = "ws://" + (window.location.port === "3000" ? "localhost:8080" : window.location.host) + "/ws/video_stream";

        var ws = new WebSocket(ws_url);
        let that = this; // cache the this
        var connectInterval;

        // websocket onopen event listener
        ws.onopen = () => {
            console.log("Connected to video websocket");

            this.ws = ws
            this.start_streaming(ws);


            that.timeout = 250; // reset timer to 250 on open of websocket connection
            clearTimeout(connectInterval); // clear Interval on on open of websocket connection
        };

        ws.onmessage = evt => {
            // listen to data sent from the websocket server
            this.new_frame(evt.data);
        }

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

    new_frame = async (frame) => {
        this.frame_counter += 1;
        var now = Date.now() / 1000;
        if (now - this.last_frame_ts > FPS_UPDATE_INTERVAL) {
            this.props.updateFps(Math.round(this.frame_counter / (now - this.last_frame_ts)))
            this.frame_counter = 0;
            this.last_frame_ts = now;
        }
        if (this.ws !== null) {
            this.ws.send("ready");
        }
        this.setState({frame: await frame.arrayBuffer()});
    }

    render() {
        let base64String = "";
        if (this.state.frame !== null) {
            var binary = '';
            var bytes = new Uint8Array( this.state.frame );
            var len = bytes.byteLength;
            for (var i = 0; i < len; i++) {
                binary += String.fromCharCode( bytes[ i ] );
            }
            base64String = btoa(binary);
        }
        let source = "logo512.png";
        if (base64String !== null) {
            source = `data:image/jpg;base64,${base64String}`;
        }
        return (
            <img
                src={source}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                alt="Camera Feed"
                onMouseMove={this.props.onMouseMove}
                onClick={this.props.onClick}
            />
        )
    }
}

export default VideoStreamControl;