import React from 'react';
import { render } from '@testing-library/react';
import VideoStreamControl from './VideoStreamControl';

const baseProps = {
  updateFps: () => {},
  sendWebRTCMessage: () => {},
  talking: false,
};

test('renders a video element', () => {
  render(<VideoStreamControl {...baseProps} />);
  expect(document.querySelector('video')).toBeInTheDocument();
});

test('renders video element with correct inline styles', () => {
  render(<VideoStreamControl {...baseProps} />);
  const video = document.querySelector('video');
  expect(video).toHaveStyle({ width: '100%', height: '100%', objectFit: 'contain' });
});

test('renders without throwing when sendWebRTCMessage and updateFps are provided', () => {
  expect(() => render(<VideoStreamControl {...baseProps} />)).not.toThrow();
});

test('renders PiP video element when talking=true', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const videos = document.querySelectorAll('video');
  expect(videos.length).toBe(2);
  const pip = videos[1];
  expect(pip.style.position).toBe('absolute');
});

test('does not render PiP video element when talking=false', () => {
  render(<VideoStreamControl {...baseProps} talking={false} />);
  const videos = document.querySelectorAll('video');
  expect(videos.length).toBe(1);
});

test('renders hidden audio element', () => {
  render(<VideoStreamControl {...baseProps} />);
  const audio = document.querySelector('audio');
  expect(audio).toBeInTheDocument();
  expect(audio.style.display).toBe('none');
});
