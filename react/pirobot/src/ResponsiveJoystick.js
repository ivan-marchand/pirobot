import React from 'react';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { Joystick } from 'react-joystick-component';

export default function ResponsiveJoystick(props) {
  const theme = useTheme();
  const isXs = useMediaQuery(theme.breakpoints.down('sm'));
  const isSm = useMediaQuery(theme.breakpoints.between('sm', 'md'));
  const size = isXs ? 120 : isSm ? 140 : 160;
  const stickSize = Math.round(size * 0.45);
  return (
    <Joystick
      {...props}
      size={size}
      stickSize={stickSize}
      sticky={false}
      baseColor="grey"
      stickColor="black"
      minDistance={2}
    />
  );
}
