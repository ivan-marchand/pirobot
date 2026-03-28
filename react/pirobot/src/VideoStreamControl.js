import React from "react";

const FPS_UPDATE_INTERVAL = 1; // seconds

class VideoStreamControl extends React.Component {
    constructor(props) {
        super(props);
        this._pc = null;
        this._frameCount = 0;
        this._lastFpsTs = 0;
        this._fpsInterval = null;
        this._videoRef = React.createRef();
    }

    componentDidMount() {
        this._startWebRTC();
    }

    componentWillUnmount() {
        this._closeWebRTC();
    }

    _startWebRTC = async () => {
        this._closeWebRTC();

        const pc = new RTCPeerConnection({ iceServers: [] });
        this._pc = pc;

        pc.ontrack = (event) => {
            if (this._videoRef.current && event.streams[0]) {
                this._videoRef.current.srcObject = event.streams[0];
                this._startFpsCounter();
            }
        };

        pc.onicecandidate = (event) => {
            if (event.candidate) {
                this.props.sendWebRTCMessage({
                    action: "ice_candidate",
                    candidate: event.candidate.candidate,
                    sdpMid: event.candidate.sdpMid,
                    sdpMLineIndex: event.candidate.sdpMLineIndex,
                });
            }
        };

        // Add a recvonly transceiver so the server knows we want video
        pc.addTransceiver("video", { direction: "recvonly" });

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        this.props.sendWebRTCMessage({
            action: "offer",
            sdp: pc.localDescription.sdp,
            type: "offer",
        });
    };

    _closeWebRTC = () => {
        if (this._pc) {
            this._pc.close();
            this._pc = null;
        }
        this._stopFpsCounter();
    };

    handleWebRTCMessage = async (msg) => {
        if (!this._pc) return;
        if (msg.action === "answer") {
            await this._pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
        } else if (msg.action === "ice_candidate") {
            await this._pc.addIceCandidate({
                candidate: msg.candidate,
                sdpMid: msg.sdpMid,
                sdpMLineIndex: msg.sdpMLineIndex,
            });
        }
    };

    _startFpsCounter = () => {
        const video = this._videoRef.current;
        if (!video) return;
        this._lastFpsTs = performance.now();
        this._frameCount = 0;

        if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
            const onFrame = (_now, _meta) => {
                this._frameCount++;
                const now = performance.now();
                if ((now - this._lastFpsTs) / 1000 >= FPS_UPDATE_INTERVAL) {
                    this.props.updateFps(
                        Math.round(this._frameCount / ((now - this._lastFpsTs) / 1000))
                    );
                    this._frameCount = 0;
                    this._lastFpsTs = now;
                }
                if (this._videoRef.current) {
                    this._videoRef.current.requestVideoFrameCallback(onFrame);
                }
            };
            video.requestVideoFrameCallback(onFrame);
        } else {
            // Safari fallback: poll with setInterval
            this._fpsInterval = setInterval(() => {
                if (video.readyState >= 2) {
                    this._frameCount++;
                    const now = performance.now();
                    if ((now - this._lastFpsTs) / 1000 >= FPS_UPDATE_INTERVAL) {
                        this.props.updateFps(
                            Math.round(this._frameCount / ((now - this._lastFpsTs) / 1000))
                        );
                        this._frameCount = 0;
                        this._lastFpsTs = now;
                    }
                }
            }, 33); // ~30 fps poll
        }
    };

    _stopFpsCounter = () => {
        if (this._fpsInterval) {
            clearInterval(this._fpsInterval);
            this._fpsInterval = null;
        }
    };

    render() {
        return (
            <video
                ref={this._videoRef}
                autoPlay
                playsInline
                muted
                style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            />
        );
    }
}

export default VideoStreamControl;
