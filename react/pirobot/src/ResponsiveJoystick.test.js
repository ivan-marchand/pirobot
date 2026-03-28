import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import ResponsiveJoystick from './ResponsiveJoystick';

jest.mock('react-joystick-component', () => ({
  Joystick: ({ size, stickSize }) => (
    <div data-testid="joystick" data-size={String(size)} data-stick-size={String(stickSize)} />
  ),
}));

jest.mock('@mui/material/useMediaQuery', () => jest.fn());

afterEach(() => useMediaQuery.mockReset());

const theme = createTheme();
const wrap = (ui) => render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);

test('uses size 80 on xs (portrait mobile)', () => {
  // first call: down('sm') = true (is xs), second call: between('sm','md') = false
  useMediaQuery.mockReturnValueOnce(true).mockReturnValueOnce(false);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '80');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '36');
});

test('uses size 100 on sm (tablet/landscape)', () => {
  // first call: down('sm') = false, second call: between('sm','md') = true
  useMediaQuery.mockReturnValueOnce(false).mockReturnValueOnce(true);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '100');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '45');
});

test('uses size 120 on desktop', () => {
  // neither xs nor sm
  useMediaQuery.mockReturnValue(false);
  wrap(<ResponsiveJoystick move={() => {}} stop={() => {}} />);
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-size', '120');
  expect(screen.getByTestId('joystick')).toHaveAttribute('data-stick-size', '54');
});
