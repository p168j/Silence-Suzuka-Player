# Button Feedback Mockups

Interactive HTML/CSS demonstrations of different button feedback styles to improve the "dead" feeling of current play/pause and control buttons.

## Files

- `style-a.html` - **Bounce Back Effect**: Current shrink + bounce back with satisfying "pop"
- `style-b.html` - **Ripple Effect**: Material Design circular ripple from click point
- `style-c.html` - **Color Pulse + Scale**: Brief color flash with scale animation
- `style-d.html` - **Kinetic + Audio-like**: Multi-stage animation with musical feel

## Testing

Open each HTML file in a browser to test the interactive feedback. Each demo includes:

- Primary play/pause button (main focus)
- Secondary control buttons (skip, previous, shuffle, repeat)
- Compact "Add Media" button
- Volume controls

## Dark Theme

All mockups are designed with dark theme compatibility matching the Silence Suzuka Player aesthetic.

## Implementation Notes

Each style includes timing, easing function, and interaction details that can be translated to the PySide6 QPropertyAnimation system used in the main application.