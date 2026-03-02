import React from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, Image, Animated, Keyboard } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Bell, Search, Mic, User } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import ActionCard from '../../components/ui/ActionCard';
import ScanIcon from '../../components/ui/icons/ScanIcon';
import CustomExportIcon from '../../components/ui/icons/CustomExportIcon';
import ExportIcon from '../../components/ui/icons/ExportIcon';
import RythmiqLogoIcon from '../../components/ui/icons/RythmiqLogoIcon';
import NotificationsPanel from '../../components/ui/NotificationsPanel';
import { router } from 'expo-router';
import { useAuth } from '../../contexts/AuthContext';
import { isDevSandboxMode } from '../../services/api';

export default function Dashboard() {
    const { user } = useAuth();
    const [notificationsPanelVisible, setNotificationsPanelVisible] = React.useState(false);
    const [unreadCount, setUnreadCount] = React.useState(0);
    const [isSearchFocused, setIsSearchFocused] = React.useState(false);
    const overlayAnim = React.useRef(new Animated.Value(0)).current;
    const searchInputRef = React.useRef<TextInput>(null);

    const greetingName = React.useMemo(() => {
        if (isDevSandboxMode()) {
            return 'Guest';
        }

        const displayName = user?.name?.trim();
        if (displayName) {
            const [firstName] = displayName.split(/\s+/);
            return firstName;
        }

        const emailLocalPart = user?.email?.split('@')[0]?.trim();
        if (emailLocalPart) {
            return emailLocalPart;
        }

        return 'Guest';
    }, [user]);

    React.useEffect(() => {
        if (isSearchFocused) {
            overlayAnim.setValue(0);
            Animated.timing(overlayAnim, {
                toValue: 1,
                duration: 220,
                useNativeDriver: true,
            }).start(() => searchInputRef.current?.focus());
        }
    }, [isSearchFocused]);

    const openSearch = () => setIsSearchFocused(true);

    const closeSearch = () => {
        Keyboard.dismiss();
        Animated.timing(overlayAnim, {
            toValue: 0,
            duration: 180,
            useNativeDriver: true,
        }).start(() => setIsSearchFocused(false));
    };

    const searchBarTranslateY = overlayAnim.interpolate({
        inputRange: [0, 1],
        outputRange: [-20, 0],
    });

    return (
        <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity
                    style={styles.headerProfileButton}
                    onPress={() => router.push('/(tabs)/profile')}
                >
                    <User size={24} color={Colors.palette.white} />
                </TouchableOpacity>
                <TouchableOpacity
                    style={styles.notificationButton}
                    onPress={() => setNotificationsPanelVisible(true)}
                >
                    <Bell size={24} color={Colors.palette.white} />
                    {unreadCount > 0 && (
                        <View style={styles.badge}>
                            <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
                        </View>
                    )}
                </TouchableOpacity>
            </View>

            {/* Greeting */}
            <View style={styles.greetingContainer}>
                <Text style={styles.greetingTitle}>Hi {greetingName},</Text>
                <Text style={styles.greetingSubtitle}>How can I help{'\n'}you today?</Text>
            </View>

            {/* Action Grid */}
            <View style={styles.gridContainer}>
                <View style={styles.row}>
                    <ActionCard
                        title="Upload"
                        description="Add new documents"
                        icon={ScanIcon}
                        onPress={() => router.push('/(tabs)/capture')}
                    />
                    <ActionCard
                        title="Custom Export"
                        description="Define your rules"
                        icon={CustomExportIcon}
                        onPress={() => console.log('Custom Export')}
                    />
                </View>
                <View style={styles.row}>
                    <ActionCard
                        title="Export"
                        description="Export for portals"
                        icon={ExportIcon}
                        onPress={() => router.push('/(tabs)/portal-selector')}
                    />
                    <ActionCard
                        title="Concierge"
                        description="We apply for you"
                        icon={RythmiqLogoIcon}
                        onPress={() => console.log('Concierge')}
                    />
                </View>
            </View>

            {/* Search Bar (tap target — not directly editable) */}
            <TouchableOpacity style={styles.searchSection} onPress={openSearch} activeOpacity={1}>
                <View style={styles.searchBar}>
                    <Search size={20} color="#999" />
                    <Text style={styles.searchPlaceholder}>Search</Text>
                    <Mic size={20} color="#999" />
                </View>
            </TouchableOpacity>

            {/* Search Overlay */}
            {isSearchFocused && (
                <View style={StyleSheet.absoluteFillObject} pointerEvents="box-none">
                    {/* Backdrop */}
                    <Animated.View
                        style={[StyleSheet.absoluteFillObject, styles.searchBackdrop, { opacity: overlayAnim }]}
                        pointerEvents="none"
                    />
                    <TouchableOpacity
                        style={StyleSheet.absoluteFillObject}
                        onPress={closeSearch}
                        activeOpacity={1}
                    />
                    {/* Animated search bar at top */}
                    <Animated.View
                        style={[
                            styles.searchOverlayBar,
                            { opacity: overlayAnim, transform: [{ translateY: searchBarTranslateY }] },
                        ]}
                        onStartShouldSetResponder={() => true}
                    >
                        <Search size={20} color="#999" />
                        <TextInput
                            ref={searchInputRef}
                            style={styles.searchInput}
                            placeholder="Search"
                            placeholderTextColor="#999"
                        />
                        <TouchableOpacity onPress={closeSearch}>
                            <Text style={styles.cancelText}>Cancel</Text>
                        </TouchableOpacity>
                    </Animated.View>
                </View>
            )}

            <NotificationsPanel
                visible={notificationsPanelVisible}
                onClose={() => setNotificationsPanelVisible(false)}
                onUnreadCountChange={setUnreadCount}
            />
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: Colors.palette.inkBlack,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 24,
        paddingTop: 8,
        paddingBottom: 16,
    },
    headerProfileButton: {
        width: 24,
        height: 24,
        alignItems: 'center',
        justifyContent: 'center',
    },
    notificationButton: {
        position: 'relative',
    },
    badge: {
        position: 'absolute',
        top: -4,
        right: -4,
        backgroundColor: '#FF6B00',
        width: 16,
        height: 16,
        borderRadius: 8,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: Colors.palette.inkBlack,
    },
    badgeText: {
        color: '#fff',
        fontSize: 10,
        fontWeight: 'bold',
    },
    greetingContainer: {
        flex: 1,
        paddingHorizontal: 24,
        justifyContent: 'flex-end',
        paddingBottom: 24,
    },
    greetingTitle: {
        fontSize: 32,
        fontWeight: '600',
        color: '#999',
        marginBottom: 4,
    },
    greetingSubtitle: {
        fontSize: 32,
        fontWeight: 'bold',
        color: Colors.palette.white,
        lineHeight: 38,
    },
    gridContainer: {
        paddingHorizontal: 24,
        gap: 12,
        marginBottom: 40,
    },
    row: {
        flexDirection: 'row',
        gap: 16,
    },
    searchSection: {
        paddingHorizontal: 24,
        marginBottom: 20,
    },
    searchBar: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey,
        height: 56,
        borderRadius: 28,
        paddingHorizontal: 20,
        gap: 12,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.05)',
    },
    searchPlaceholder: {
        flex: 1,
        color: '#999',
        fontSize: 16,
    },
    searchInput: {
        flex: 1,
        color: Colors.palette.white,
        fontSize: 16,
        height: '100%',
    },
    searchBackdrop: {
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
    },
    searchOverlayBar: {
        position: 'absolute',
        top: 60,
        left: 24,
        right: 24,
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey,
        height: 56,
        borderRadius: 28,
        paddingHorizontal: 20,
        gap: 12,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.1)',
    },
    cancelText: {
        color: '#999',
        fontSize: 14,
    },
});
