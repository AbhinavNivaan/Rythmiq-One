import React from 'react';
import Svg, { Path } from 'react-native-svg';

interface RythmiqLogoIconProps {
    size?: number;
    color?: string;
}

export default function RythmiqLogoIcon({ size = 24, color = 'white' }: RythmiqLogoIconProps) {
    return (
        <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
            <Path
                d="M17.1498 22.8002V30.8998H14.0502V22.8002H17.1498ZM11.6039 21.7875L5.87734 27.5141L3.68594 25.3227L9.4125 19.5961L11.6039 21.7875ZM27.5141 25.3227L25.3227 27.5141L19.5961 21.7875L21.7875 19.5961L27.5141 25.3227ZM8.3998 14.0502V17.1498H0.300194V14.0502H8.3998ZM30.8998 14.0502V17.1498H22.8002V14.0502H30.8998ZM11.6039 9.41251L9.4125 11.6039L3.80996 6.00137V5.7504L3.89785 5.66251L5.66543 3.89786L5.87734 3.68594L11.6039 9.41251ZM27.5141 5.87735L21.7875 11.6039L19.5961 9.41251L25.3227 3.68594L27.5141 5.87735ZM17.1498 0.300201V8.39981H14.0502V0.300201H17.1498Z"
                fill={color}
                stroke={color}
                strokeWidth="0.6"
            />
        </Svg>
    );
}
