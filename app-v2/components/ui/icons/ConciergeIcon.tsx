import React from 'react';
import Svg, { Path, Circle } from 'react-native-svg';

interface ConciergeIconProps {
    size?: number;
    color?: string;
}

export default function ConciergeIcon({ size = 24, color = 'white' }: ConciergeIconProps) {
    return (
        <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
            {/* Person silhouette */}
            <Circle
                cx="12"
                cy="7"
                r="3"
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            <Path
                d="M6 21V19C6 16.7909 7.79086 15 10 15H14C16.2091 15 18 16.7909 18 19V21"
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            {/* Helping hand/clipboard element */}
            <Path
                d="M16 11H20C20.5523 11 21 11.4477 21 12V14C21 14.5523 20.5523 15 20 15H16"
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            <Path
                d="M18 13H19"
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </Svg>
    );
}
