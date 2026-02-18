import { View, Text, TouchableOpacity, StyleSheet, Dimensions } from 'react-native';
import { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Layers, User, Plus } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import { router } from 'expo-router';

export default function CustomTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
    return (
        <View style={styles.container}>
            <View style={styles.content}>
                {/* Left Group */}
                <View style={styles.leftGroup}>
                    {/* Dashboard / Home Tab */}
                    <TouchableOpacity
                        style={[styles.tabButton, state.index === 0 && styles.activeTab]}
                        onPress={() => navigation.navigate('dashboard')}
                    >
                        <Layers size={24} color={state.index === 0 ? Colors.palette.inkBlack : Colors.palette.white} />
                    </TouchableOpacity>

                    {/* Profile Tab (Placeholder for now, navigates to profile eventually) */}
                    <TouchableOpacity
                        style={styles.tabButton}
                        onPress={() => console.log('Profile')}
                    >
                        <User size={24} color="#666" />
                    </TouchableOpacity>
                </View>

                {/* Right Group / FAB */}
                <TouchableOpacity style={styles.fab} onPress={() => console.log('FAB Press')}>
                    <Plus size={24} color={Colors.palette.white} />
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        position: 'absolute',
        bottom: 24,
        left: 0,
        right: 0,
        alignItems: 'center',
        paddingHorizontal: 24,
    },
    content: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        width: '100%',
        alignItems: 'flex-end',
    },
    leftGroup: {
        flexDirection: 'row',
        backgroundColor: Colors.palette.shadowGrey, // Pill shape background
        borderRadius: 32,
        padding: 6,
        gap: 8,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.1)',
    },
    tabButton: {
        width: 52,
        height: 52,
        borderRadius: 26,
        alignItems: 'center',
        justifyContent: 'center',
    },
    activeTab: {
        backgroundColor: Colors.palette.white,
    },
    fab: {
        width: 64,
        height: 64,
        borderRadius: 32,
        backgroundColor: Colors.palette.inkBlack, // Dark button
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.2)',
        // Shadow
        shadowColor: "#000",
        shadowOffset: {
            width: 0,
            height: 4,
        },
        shadowOpacity: 0.3,
        shadowRadius: 4.65,
        elevation: 8,
    }
});
