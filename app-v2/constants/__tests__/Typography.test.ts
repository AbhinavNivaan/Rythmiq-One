import Typography from '../Typography';

const REQUIRED_KEYS = ['nano', 'caption', 'label', 'body', 'button', 'titleSm', 'titleMd', 'titleLg'] as const;

describe('Typography scale', () => {
  it.each(REQUIRED_KEYS)('%s has fontSize and fontFamily', (key) => {
    const style = Typography[key];
    expect(typeof style.fontSize).toBe('number');
    expect(typeof style.fontFamily).toBe('string');
  });

  it('nano is 10px Satoshi-Medium', () => {
    expect(Typography.nano.fontSize).toBe(10);
    expect(Typography.nano.fontFamily).toBe('Satoshi-Medium');
  });
  it('button is 16px Satoshi-Bold with letterSpacing 0.3', () => {
    expect(Typography.button.fontSize).toBe(16);
    expect(Typography.button.fontFamily).toBe('Satoshi-Bold');
    expect(Typography.button.letterSpacing).toBe(0.3);
  });
  it('titleLg is 32px Satoshi-Black', () => {
    expect(Typography.titleLg.fontSize).toBe(32);
    expect(Typography.titleLg.fontFamily).toBe('Satoshi-Black');
  });
});
