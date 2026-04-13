import { getInputStyles } from '../Input';
import Colors from '../../../constants/Colors';

describe('getInputStyles — resting', () => {
  it('uses surface fill and border-subtle', () => {
    const s = getInputStyles({ focused: false, error: false, disabled: false });
    expect(s.container.backgroundColor).toBe(Colors.semantic.surface);
    expect(s.container.borderColor).toBe(Colors.semantic.borderSubtle);
    expect(s.container.borderWidth).toBe(1);
  });
});

describe('getInputStyles — focused', () => {
  it('uses surfaceElevated fill and green border', () => {
    const s = getInputStyles({ focused: true, error: false, disabled: false });
    expect(s.container.backgroundColor).toBe(Colors.semantic.surfaceElevated);
    expect(s.container.borderColor).toBe(Colors.semantic.borderFocus);
    expect(s.container.borderWidth).toBe(1.5);
  });
  it('icon colour is accent green', () => {
    const s = getInputStyles({ focused: true, error: false, disabled: false });
    expect(s.iconColor).toBe(Colors.semantic.accent);
  });
});

describe('getInputStyles — error', () => {
  it('uses surface fill and red border', () => {
    const s = getInputStyles({ focused: false, error: true, disabled: false });
    expect(s.container.backgroundColor).toBe(Colors.semantic.surface);
    expect(s.container.borderColor).toBe(Colors.semantic.borderError);
    expect(s.container.borderWidth).toBe(1.5);
  });
  it('icon colour is red', () => {
    const s = getInputStyles({ focused: false, error: true, disabled: false });
    expect(s.iconColor).toBe(Colors.palette.red);
  });
});

describe('getInputStyles — disabled', () => {
  it('uses neutral-0 fill and dashed border', () => {
    const s = getInputStyles({ focused: false, error: false, disabled: true });
    expect(s.container.backgroundColor).toBe(Colors.palette.neutral0);
    expect(s.container.borderStyle).toBe('dashed');
    expect(s.container.borderWidth).toBe(1.5);
  });
  it('focused is ignored when disabled', () => {
    const s = getInputStyles({ focused: true, error: false, disabled: true });
    expect(s.container.backgroundColor).toBe(Colors.palette.neutral0);
  });
});
