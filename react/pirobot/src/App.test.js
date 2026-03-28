import { render } from '@testing-library/react';
import App from './App';

// suppress WebSocket noise
global.WebSocket = class {
  constructor() { this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null; }
  send() {}
  close() {}
};

// suppress VideoStreamControl WebRTC (RTCPeerConnection not available in jsdom)
jest.mock('./VideoStreamControl', () => {
  const { forwardRef } = require('react');
  return { __esModule: true, default: forwardRef((_props, _ref) => <div data-testid="video-stream" />) };
});

// suppress Joystick canvas errors
jest.mock('./ResponsiveJoystick', () => () => <div data-testid="joystick" />);

test('renders without crashing', () => {
  expect(() => render(<App />)).not.toThrow();
});
