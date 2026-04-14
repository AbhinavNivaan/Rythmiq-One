const palette = {
  neutral0:   '#070712',
  neutral100: '#191B26',
  neutral200: '#23263a',
  neutral900: '#FCFEFF',
  green:  '#4ADE80',
  blue:   '#60A5FA',
  blue400: '#89C7FE',
  amber:  '#FF9500',
  red:    '#EF4444',
  // Legacy aliases — screens still reference these; remove after screen remediation
  inkBlack:   '#070712',
  shadowGrey: '#191B26',
  white:      '#FCFEFF',
} as const;

const semantic = {
  // Surfaces
  background:      palette.neutral0,
  surface:         palette.neutral100,
  surfaceElevated: palette.neutral200,
  // Borders
  borderSubtle:  'rgba(255,255,255,0.05)',
  borderDefault: 'rgba(255,255,255,0.10)',
  borderFocus:   palette.green,
  borderError:   palette.red,
  // Text
  textPrimary:   palette.neutral900,
  textSecondary: '#999999',
  textError:     palette.red,
  textLink:      palette.green,
  // Accent
  accent: palette.green,
  // Status
  statusPending:    palette.amber,
  statusProcessing: palette.green,
  statusCompleted:  palette.blue,
  statusFailed:     palette.red,
} as const;

const Colors = {
  palette,
  semantic,
  backdrop: 'rgba(0,0,0,0.75)',
  disabled: {
    fill: 'rgba(255,255,255,0.10)',
    text: 'rgba(255,255,255,0.25)',
  },
} as const;

export default Colors;
