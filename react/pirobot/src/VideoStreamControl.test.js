import React from 'react';
import { render, screen } from '@testing-library/react';
import VideoStreamControl from './VideoStreamControl';

test('renders a video element', () => {
  render(
    <VideoStreamControl
      updateFps={() => {}}
      sendWebRTCMessage={() => {}}
    />
  );
  expect(document.querySelector('video')).toBeInTheDocument();
});

test('renders video element with correct inline styles', () => {
  render(
    <VideoStreamControl
      updateFps={() => {}}
      sendWebRTCMessage={() => {}}
    />
  );
  const video = document.querySelector('video');
  expect(video).toHaveStyle({ width: '100%', height: '100%', objectFit: 'contain' });
});

test('renders without throwing when sendWebRTCMessage and updateFps are provided', () => {
  expect(() =>
    render(
      <VideoStreamControl
        updateFps={() => {}}
        sendWebRTCMessage={() => {}}
      />
    )
  ).not.toThrow();
});
