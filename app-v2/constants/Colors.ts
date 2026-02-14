const tintColorLight = '#1A2595'; // True Cobalt
const tintColorDark = '#89C7FE'; // Maya Blue

export default {
    light: {
        text: '#070712', // Ink Black
        background: '#FCFEFF', // White
        tint: tintColorLight,
        tabIconDefault: '#ccc',
        tabIconSelected: tintColorLight,
    },
    dark: {
        text: '#FCFEFF', // White
        background: '#070712', // Ink Black
        tint: tintColorDark,
        tabIconDefault: '#ccc',
        tabIconSelected: tintColorDark,
        primary: '#1A2595', // True Cobalt
        secondary: '#89C7FE', // Maya Blue
        surface: '#191B26', // Shadow Grey
        border: 'rgba(255, 255, 255, 0.1)',
    },
    // Adding explicit palette for direct usage
    palette: {
        white: '#FCFEFF',
        mayaBlue: '#89C7FE',
        trueCobalt: '#1A2595',
        shadowGrey: '#191B26',
        inkBlack: '#070712',
    }
};
