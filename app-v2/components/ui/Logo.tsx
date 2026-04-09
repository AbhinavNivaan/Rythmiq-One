import { View } from 'react-native';
import Svg, { Rect } from 'react-native-svg';

interface LogoProps {
    size?: number;
    color?: string;
}

export default function Logo({ size = 150, color = '#FFFFFF' }: LogoProps) {
    const angles = [0, 45, 90, 135, 180, 225, 270, 315];

    return (
        <View style={{ width: size, height: size, justifyContent: 'center', alignItems: 'center' }}>
            <Svg width={size} height={size} viewBox="0 0 32 32">
                {angles.map((angle) => (
                    <Rect
                        key={angle}
                        x={14.4}
                        y={1.5}
                        width={3.2}
                        height={9}
                        rx={1.6}
                        ry={1.6}
                        fill={color}
                        transform={`rotate(${angle}, 16, 16)`}
                    />
                ))}
            </Svg>
        </View>
    );
}
