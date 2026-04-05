import React from "react";
import IconButton from '@mui/material/IconButton';
import MicIcon from '@mui/icons-material/Mic';
import MicOffIcon from '@mui/icons-material/MicOff';
import VideocamIcon from '@mui/icons-material/Videocam';
import VideocamOffIcon from '@mui/icons-material/VideocamOff';

const FPS_UPDATE_INTERVAL = 1; // seconds

class VideoStreamControl extends React.Component {
    constructor(props) {
        super(props);
        this._pc = null;
        this._localStream = null;
        this._pendingCandidates = [];
        this._frameCount = 0;
        this._lastFpsTs = 0;
        this._fpsInterval = null;
        this._videoRef = React.createRef();
        this._audioRef = React.createRef();
        this._pipRef = React.createRef();
        this.state = {
            muted: false,
            cameraOff: false,
        };
    }

    componentDidMount() {
        this._startWebRTC(this.props.talking || false);
    }

    componentDidUpdate(prevProps) {
        if (prevProps.talking !== this.props.talking) {
            this._startWebRTC(this.props.talking || false);
        }
    }

    componentWillUnmount() {
        this._closeWebRTC();
    }

    _startWebRTC = async (talking = false) => {
        this._closeWebRTC();
        this.setState({ muted: false, cameraOff: false });
        this._pendingCandidates = [];

        if (talking) {
            if (!navigator.mediaDevices) {
                console.warn("getUserMedia unavailable (requires HTTPS or localhost)");
            } else {
                try {
                    this._localStream = await navigator.mediaDevices.getUserMedia({
                        audio: true,
                        video: { width: { max: 320 }, height: { max: 240 } },
                    });
                } catch (err) {
                    console.error("getUserMedia failed:", err);
                }
            }
        }

        const pc = new RTCPeerConnection({ iceServers: [] });
        this._pc = pc;

        pc.ontrack = (event) => {
            if (event.track.kind === "video") {
                if (this._videoRef.current) {
                    this._videoRef.current.srcObject = event.streams[0];
                    this._videoRef.current.play().catch(() => {});
                    const receiver = pc.getReceivers().find(r => r.track.kind === "video");
                    if (receiver && "jitterBufferTarget" in receiver) {
                        receiver.jitterBufferTarget = 0;
                    }
                    this._startFpsCounter();
                }
            } else if (event.track.kind === "audio") {
                if (this._audioRef.current) {
                    this._audioRef.current.srcObject = event.streams[0];
                }
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

        pc.addTransceiver("video", { direction: "recvonly" });

        if (talking && this._localStream) {
            pc.addTransceiver("audio", { direction: "recvonly" });
            const audioTrack = this._localStream.getAudioTracks()[0];
            const videoTrack = this._localStream.getVideoTracks()[0];
            if (audioTrack) pc.addTransceiver(audioTrack, { direction: "sendonly" });
            if (videoTrack) pc.addTransceiver(videoTrack, { direction: "sendonly" });
            if (this._pipRef.current) {
                this._pipRef.current.srcObject = this._localStream;
            }
        }

        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            this.props.sendWebRTCMessage({
                action: "offer",
                sdp: pc.localDescription.sdp,
                type: "offer",
                talking: talking,
            });
        } catch (err) {
            console.error("WebRTC offer failed:", err);
        }
    };

    _closeWebRTC = () => {
        if (this._localStream) {
            this._localStream.getTracks().forEach(t => t.stop());
            this._localStream = null;
        }
        if (this._pc) {
            this._pc.close();
            this._pc = null;
        }
        if (this._videoRef.current) {
            this._videoRef.current.srcObject = null;
        }
        if (this._audioRef.current) {
            this._audioRef.current.srcObject = null;
        }
        this._pendingCandidates = [];
        this._stopFpsCounter();
    };

    handleWebRTCMessage = async (msg) => {
        if (!this._pc) return;
        if (msg.action === "answer") {
            try {
                await this._pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
                for (const c of this._pendingCandidates) {
                    await this._pc.addIceCandidate(c).catch(err =>
                        console.warn("Buffered ICE candidate failed:", err)
                    );
                }
                this._pendingCandidates = [];
            } catch (err) {
                console.warn("setRemoteDescription failed:", err);
            }
        } else if (msg.action === "ice_candidate") {
            const candidate = {
                candidate: msg.candidate,
                sdpMid: msg.sdpMid,
                sdpMLineIndex: msg.sdpMLineIndex,
            };
            if (this._pc.remoteDescription) {
                await this._pc.addIceCandidate(candidate).catch(err =>
                    console.warn("ICE candidate failed:", err)
                );
            } else {
                this._pendingCandidates.push(candidate);
            }
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
            }, 33);
        }
    };

    _stopFpsCounter = () => {
        if (this._fpsInterval) {
            clearInterval(this._fpsInterval);
            this._fpsInterval = null;
        }
        this._frameCount = 0;
        this._lastFpsTs = 0;
        this.props.updateFps(0);
    };

    toggleMuted = () => {
        const track = this._localStream?.getAudioTracks()[0];
        if (track) track.enabled = !track.enabled;
        this.setState({ muted: !this.state.muted });
    };

    toggleCamera = () => {
        const track = this._localStream?.getVideoTracks()[0];
        if (track) track.enabled = !track.enabled;
        this.setState({ cameraOff: !this.state.cameraOff });
    };

    render() {
        return (
            <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                <video
                    ref={this._videoRef}
                    autoPlay
                    playsInline
                    muted
                    style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
                />
                <audio ref={this._audioRef} autoPlay style={{ display: "none" }} />
                {this.props.talking && (
                    <div style={{
                        position: "absolute",
                        bottom: 8,
                        right: 8,
                        width: 120,
                        height: 90,
                        borderRadius: 4,
                        border: "2px solid white",
                        overflow: "hidden",
                    }}>
                        {this.state.cameraOff && (
                            <div
                                data-testid="camera-off-placeholder"
                                style={{
                                    position: "absolute",
                                    inset: 0,
                                    background: "#111",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                }}
                            >
                                <VideocamOffIcon style={{ color: "white", fontSize: 32 }} />
                            </div>
                        )}
                        <video
                            ref={this._pipRef}
                            autoPlay
                            playsInline
                            muted
                            style={{
                                width: "100%",
                                height: "100%",
                                objectFit: "cover",
                                display: this.state.cameraOff ? "none" : "block",
                            }}
                        />
                        <div style={{
                            position: "absolute",
                            bottom: 0,
                            left: 0,
                            right: 0,
                            background: "rgba(0,0,0,0.45)",
                            display: "flex",
                            justifyContent: "center",
                        }}>
                            <IconButton
                                size="small"
                                onClick={this.toggleMuted}
                                aria-label={this.state.muted ? "Unmute microphone" : "Mute microphone"}
                                sx={{ color: "white", padding: "2px" }}
                            >
                                {this.state.muted
                                    ? <MicOffIcon fontSize="small" />
                                    : <MicIcon fontSize="small" />}
                            </IconButton>
                            <IconButton
                                size="small"
                                onClick={this.toggleCamera}
                                aria-label={this.state.cameraOff ? "Turn on camera" : "Turn off camera"}
                                sx={{ color: "white", padding: "2px" }}
                            >
                                {this.state.cameraOff
                                    ? <VideocamOffIcon fontSize="small" />
                                    : <VideocamIcon fontSize="small" />}
                            </IconButton>
                        </div>
                    </div>
                )}
            </div>
        );
    }
}

export default VideoStreamControl;
