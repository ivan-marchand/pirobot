// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Mock RTCPeerConnection for jsdom (not available in test environment)
global.RTCPeerConnection = class {
    constructor() {
        this.ontrack = null;
        this.onicecandidate = null;
    }
    addTransceiver() {}
    createOffer() { return Promise.resolve({ sdp: "", type: "offer" }); }
    setLocalDescription() { return Promise.resolve(); }
    setRemoteDescription() { return Promise.resolve(); }
    addIceCandidate() { return Promise.resolve(); }
    close() {}
    get localDescription() { return { sdp: "", type: "offer" }; }
};
