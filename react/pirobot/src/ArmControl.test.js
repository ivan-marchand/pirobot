import React from 'react';
import { render } from '@testing-library/react';
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

test('sliders use fluid width via sx prop (no inline width style)', () => {
  const { container } = render(
    <ThemeProvider theme={theme}>
      <ArmControl enabled={true} status={status} move={() => {}} stop={() => {}} move_limb={() => {}} />
    </ThemeProvider>
  );
  const sliders = container.querySelectorAll('.MuiSlider-root');
  expect(sliders.length).toBeGreaterThan(0);
  sliders.forEach((slider) => {
    expect(slider.style.width).toBe('');
  });
});
