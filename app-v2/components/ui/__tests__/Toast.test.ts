import { getToastStyles } from '../Toast';
import Colors from '../../../constants/Colors';

describe('getToastStyles', () => {
  it('success: green tint fill + green border', () => {
    const s = getToastStyles('success');
    expect(s.container.backgroundColor).toBe('rgba(74,222,128,0.10)');
    expect(s.container.borderColor).toBe('rgba(74,222,128,0.20)');
    expect(s.dotColor).toBe(Colors.palette.green);
    expect(s.textColor).toBe(Colors.palette.green);
  });
  it('error: red tint fill + red border', () => {
    const s = getToastStyles('error');
    expect(s.container.backgroundColor).toBe('rgba(239,68,68,0.10)');
    expect(s.container.borderColor).toBe('rgba(239,68,68,0.20)');
    expect(s.dotColor).toBe(Colors.palette.red);
    expect(s.textColor).toBe(Colors.palette.red);
  });
  it('info: blue tint fill + blue border', () => {
    const s = getToastStyles('info');
    expect(s.container.backgroundColor).toBe('rgba(96,165,250,0.10)');
    expect(s.container.borderColor).toBe('rgba(96,165,250,0.20)');
    expect(s.dotColor).toBe(Colors.palette.blue);
    expect(s.textColor).toBe(Colors.palette.blue);
  });
});
