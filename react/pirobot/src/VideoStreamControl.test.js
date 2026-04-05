import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
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

test('renders mute and camera buttons when talking=true', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn off camera/i })).toBeInTheDocument();
});

test('clicking mute button toggles aria-label', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const muteBtn = screen.getByRole('button', { name: /mute microphone/i });
  fireEvent.click(muteBtn);
  expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();
});

test('clicking mute button twice returns to unmuted state', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const muteBtn = screen.getByRole('button', { name: /mute microphone/i });
  fireEvent.click(muteBtn);
  fireEvent.click(screen.getByRole('button', { name: /unmute microphone/i }));
  expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
});

test('clicking camera button shows camera-off placeholder', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const camBtn = screen.getByRole('button', { name: /turn off camera/i });
  fireEvent.click(camBtn);
  expect(screen.getByTestId('camera-off-placeholder')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn on camera/i })).toBeInTheDocument();
});

test('PiP video element stays in DOM when camera is off', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  fireEvent.click(screen.getByRole('button', { name: /turn off camera/i }));
  const videos = document.querySelectorAll('video');
  const pip = videos[1];
  expect(pip).toBeInTheDocument();
  expect(pip.style.display).toBe('none');
});

test('renders without error when listening=true and talking=false', () => {
  expect(() => render(<VideoStreamControl {...baseProps} listening={true} />)).not.toThrow();
});
