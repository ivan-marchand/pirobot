import React from "react";

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
        this._pendingCandidates = [];

        if (talking) {
            if (!navigator.mediaDevices) {
                console.warn("getUserMedia unavailable (requires HTTPS or localhost)");
            } else {
                try {
                    this._localStream = await navigator.mediaDevices.getUserMedia({
                        audio: true,
                        video: { width: { ideal: 240 }, height: { ideal: 180 } },
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
                    <video
                        ref={this._pipRef}
                        autoPlay
                        playsInline
                        muted
                        style={{
                            position: "absolute",
                            bottom: 8,
                            right: 8,
                            width: 120,
                            height: 90,
                            objectFit: "cover",
                            borderRadius: 4,
                            border: "2px solid white",
                        }}
                    />
                )}
            </div>
        );
    }
}

export default VideoStreamControl;
