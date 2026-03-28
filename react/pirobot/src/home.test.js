import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { MemoryRouter } from 'react-router-dom';
import Home from './home';

// suppress WebSocket
global.WebSocket = class {
  constructor() { this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null; }
  send() {}
  close() {}
};

// suppress Joystick canvas errors
jest.mock('./ResponsiveJoystick', () => () => <div data-testid="joystick" />);

const theme = createTheme();
const wrap = (ui) => render(
  <ThemeProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ThemeProvider>
);

test('overflow menu button is present', () => {
  wrap(<Home />);
  expect(screen.getByLabelText('More actions')).toBeInTheDocument();
});

test('overflow menu opens when more button is clicked', () => {
  wrap(<Home />);
  fireEvent.click(screen.getByLabelText('More actions'));
  // After clicking, overflowOpen=true — the Collapse renders its children into the DOM
  expect(screen.getAllByLabelText('Open photo gallery').length).toBeGreaterThan(0);
});
