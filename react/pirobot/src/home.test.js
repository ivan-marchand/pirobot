import { render, screen, fireEvent, act } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { MemoryRouter } from 'react-router-dom';
import Home from './home';

class MockWebSocket {
  constructor() { this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null; this.readyState = 1; }
  send() {}
  close() {}
}
MockWebSocket.CLOSED = 3;
global.WebSocket = MockWebSocket;

jest.mock('./ResponsiveJoystick', () => () => <div data-testid="joystick" />);
jest.mock('./VideoStreamControl', () => {
  const { forwardRef } = require('react');
  return { __esModule: true, default: forwardRef((_props, _ref) => <div data-testid="video-stream" />) };
});

const theme = createTheme();
const wrap = (ui) => render(
  <ThemeProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ThemeProvider>
);

test('stop robot button is always visible in unified toolbar', () => {
  wrap(<Home />);
  expect(screen.getByRole('button', { name: /stop robot/i })).toBeInTheDocument();
});

test('control toggle button switches between joystick and d-pad', () => {
  wrap(<Home />);
  const dpadBtn = screen.getByRole('button', { name: /use d-pad/i });
  expect(dpadBtn).toBeInTheDocument();
  fireEvent.click(dpadBtn);
  expect(screen.getByRole('button', { name: /use joystick/i })).toBeInTheDocument();
});

test('mic button is not visible when robot_has_microphone is not set', () => {
  wrap(<Home />);
  expect(screen.queryByRole('button', { name: /start talking/i })).not.toBeInTheDocument();
});

test('mic button is visible when robot_config.robot_has_microphone is true', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  expect(screen.getByRole('button', { name: /start talking/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});

test('mic button toggles to stop talking on click', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  fireEvent.click(screen.getByRole('button', { name: /start talking/i }));
  expect(screen.getByRole('button', { name: /stop talking/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});

test('listen button is not visible when robot_has_microphone is not set', () => {
  wrap(<Home />);
  expect(screen.queryByRole('button', { name: /listen to robot/i })).not.toBeInTheDocument();
});

test('listen button is visible when robot_config.robot_has_microphone is true', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  expect(screen.getByRole('button', { name: /listen to robot/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});

test('listen button toggles to stop listening on click', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  fireEvent.click(screen.getByRole('button', { name: /listen to robot/i }));
  expect(screen.getByRole('button', { name: /stop listening/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});
