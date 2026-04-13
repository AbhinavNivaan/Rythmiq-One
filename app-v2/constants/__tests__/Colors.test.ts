import Colors from '../Colors';

describe('Colors — primitive tokens', () => {
  it('has all 8 primitive tokens with correct values', () => {
    expect(Colors.palette.neutral0).toBe('#070712');
    expect(Colors.palette.neutral100).toBe('#191B26');
    expect(Colors.palette.neutral200).toBe('#23263a');
    expect(Colors.palette.neutral900).toBe('#FCFEFF');
    expect(Colors.palette.green).toBe('#4ADE80');
    expect(Colors.palette.blue).toBe('#60A5FA');
    expect(Colors.palette.amber).toBe('#FF9500');
    expect(Colors.palette.red).toBe('#EF4444');
  });
});

describe('Colors — semantic aliases', () => {
  it('background maps to neutral0', () => {
    expect(Colors.semantic.background).toBe(Colors.palette.neutral0);
  });
  it('surface maps to neutral100', () => {
    expect(Colors.semantic.surface).toBe(Colors.palette.neutral100);
  });
  it('surfaceElevated maps to neutral200', () => {
    expect(Colors.semantic.surfaceElevated).toBe(Colors.palette.neutral200);
  });
  it('accent maps to green', () => {
    expect(Colors.semantic.accent).toBe(Colors.palette.green);
  });
  it('statusCompleted maps to blue (not green)', () => {
    expect(Colors.semantic.statusCompleted).toBe(Colors.palette.blue);
  });
  it('statusProcessing maps to green', () => {
    expect(Colors.semantic.statusProcessing).toBe(Colors.palette.green);
  });
  it('has backdrop defined', () => {
    expect(Colors.backdrop).toBeDefined();
  });
  it('disabled fill and text are defined', () => {
    expect(Colors.disabled.fill).toBeDefined();
    expect(Colors.disabled.text).toBeDefined();
  });
});
