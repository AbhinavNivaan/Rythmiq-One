import { getButtonStyles } from '../Button';
import Colors from '../../../constants/Colors';

describe('getButtonStyles — fill', () => {
  it('primary-white: white fill', () => {
    const s = getButtonStyles('primary-white', false);
    expect(s.container.backgroundColor).toBe(Colors.palette.neutral900);
  });
  it('primary-green: green fill', () => {
    const s = getButtonStyles('primary-green', false);
    expect(s.container.backgroundColor).toBe(Colors.palette.green);
  });
  it('secondary: green at 12% opacity fill', () => {
    const s = getButtonStyles('secondary', false);
    expect(s.container.backgroundColor).toBe('rgba(74,222,128,0.12)');
  });
  it('soft-danger: red at 12% opacity fill', () => {
    const s = getButtonStyles('soft-danger', false);
    expect(s.container.backgroundColor).toBe('rgba(239,68,68,0.12)');
  });
  it('ghost: transparent fill', () => {
    const s = getButtonStyles('ghost', false);
    expect(s.container.backgroundColor).toBe('transparent');
  });
  it('ghost-outline: transparent fill with border', () => {
    const s = getButtonStyles('ghost-outline', false);
    expect(s.container.backgroundColor).toBe('transparent');
    expect(s.container.borderWidth).toBe(1.5);
  });
  it('danger: transparent fill with red border', () => {
    const s = getButtonStyles('danger', false);
    expect(s.container.backgroundColor).toBe('transparent');
    expect(s.container.borderColor).toBe(Colors.palette.red);
  });
  it('icon-round: surface fill, 46x46 circle', () => {
    const s = getButtonStyles('icon-round', false);
    expect(s.container.backgroundColor).toBe(Colors.semantic.surface);
    expect(s.container.width).toBe(46);
    expect(s.container.height).toBe(46);
    expect(s.container.borderRadius).toBe(23);
  });
});

describe('getButtonStyles — text colour', () => {
  it('primary-white: inkBlack text', () => {
    expect(getButtonStyles('primary-white', false).textColor).toBe(Colors.palette.neutral0);
  });
  it('primary-green: inkBlack text', () => {
    expect(getButtonStyles('primary-green', false).textColor).toBe(Colors.palette.neutral0);
  });
  it('secondary: green text', () => {
    expect(getButtonStyles('secondary', false).textColor).toBe(Colors.palette.green);
  });
  it('soft-danger: red text', () => {
    expect(getButtonStyles('soft-danger', false).textColor).toBe(Colors.palette.red);
  });
  it('danger: red text', () => {
    expect(getButtonStyles('danger', false).textColor).toBe(Colors.palette.red);
  });
});

describe('getButtonStyles — disabled overrides all variants', () => {
  const variants = ['primary-white', 'primary-green', 'secondary', 'soft-danger', 'ghost', 'ghost-outline', 'danger'] as const;
  it.each(variants)('%s disabled: uses disabled fill token', (variant) => {
    const s = getButtonStyles(variant, true);
    expect(s.container.backgroundColor).toBe(Colors.disabled.fill);
    expect(s.textColor).toBe(Colors.disabled.text);
  });
});
