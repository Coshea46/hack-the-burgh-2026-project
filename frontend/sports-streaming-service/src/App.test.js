import { render, screen, fireEvent } from '@testing-library/react';
import App from './App';

test('shows all 7 feeds in the grid', () => {
  render(<App />);
  for (let i = 1; i <= 7; i++) {
    expect(screen.getByLabelText(`Match ${i}`)).toBeInTheDocument();
  }
});

test('clicking a feed focuses it and Esc returns to the grid', () => {
  render(<App />);
  fireEvent.click(screen.getByLabelText('Match 3'));
  expect(screen.getByText('← All matches')).toBeInTheDocument();
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByText('← All matches')).not.toBeInTheDocument();
});
