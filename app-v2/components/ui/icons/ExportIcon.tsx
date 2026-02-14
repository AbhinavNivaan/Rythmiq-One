import React from 'react';
import Svg, { Path, G } from 'react-native-svg';

interface ExportIconProps {
    size?: number;
    color?: string;
}

export default function ExportIcon({ size = 24, color = 'white' }: ExportIconProps) {
    return (
        <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
            <G>
                <Path
                    d="M12 20C7.58172 20 4 16.4183 4 12M20 12C20 14.5264 18.8289 16.7792 17 18.2454"
                    stroke={color}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                />
                <Path
                    d="M12 14L12 4M12 4L15 7M12 4L9 7"
                    stroke={color}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            </G>
        </Svg>
    );
}
