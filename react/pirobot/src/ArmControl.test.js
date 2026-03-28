import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import ArmControl from './ArmControl';

const theme = createTheme();

const status = {
  config: {
    shoulder: { max_angle: 180 },
    forearm:  { max_angle: 180 },
    wrist:    { max_angle: 180 },
    claw:     { max_angle: 180 },
  },
  position: { shoulder: 0, forearm: 0, wrist: 0, claw: 0 },
};

test('renders sliders without fixed pixel widths', () => {
  const { container } = render(
    <ThemeProvider theme={theme}>
      <ArmControl enabled={true} status={status} move={() => {}} stop={() => {}} move_limb={() => {}} />
    </ThemeProvider>
  );
  const sliders = container.querySelectorAll('.MuiSlider-root');
  sliders.forEach((slider) => {
    expect(slider).not.toHaveStyle({ width: '150px' });
  });
});
