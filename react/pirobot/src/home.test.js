import { render, screen, fireEvent } from '@testing-library/react';
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
