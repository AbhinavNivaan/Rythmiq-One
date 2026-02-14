import React from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { HelpCircle, Bell, Search, Mic, User, Plus } from 'lucide-react-native';
import Colors from '../../constants/Colors';
import ActionCard from '../../components/ui/ActionCard';
import LayersDocumentIcon from '../../components/ui/LayersDocumentIcon';
import ScanIcon from '../../components/ui/icons/ScanIcon';
import CustomExportIcon from '../../components/ui/icons/CustomExportIcon';
import ExportIcon from '../../components/ui/icons/ExportIcon';
import RythmiqLogoIcon from '../../components/ui/icons/RythmiqLogoIcon';
import { router } from 'expo-router';

export default function Dashboard() {
    return (
        <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
            {/* Dev Sandbox Banner - only shows in dev sandbox mode */}
            
            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity>
                    <HelpCircle size={24} color={Colors.palette.white} />
                </TouchableOpacity>
                <TouchableOpacity style={styles.notificationButton}>
                    <Bell size={24} color={Colors.palette.white} />
                    <View style={styles.badge}>
                        <Text style={styles.badgeText}>4</Text>
                    </View>
                </TouchableOpacity>
            </View>

            {/* Greeting */}
            <View style={styles.greetingContainer}>
                <Text style={styles.greetingTitle}>Hi Kelvin,</Text>
                <Text style={styles.greetingSubtitle}>How can I help{'\n'}you today?</Text>
            </View>

            {/* Action Grid */}
            <View style={styles.gridContainer}>
                <View style={styles.row}>
                    <ActionCard
                        title="Scan"
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

            {/* Search Bar */}
            <View style={styles.searchSection}>
                <View style={styles.searchBar}>
                    <Search size={20} color="#999" />
                    <TextInput
                        style={styles.searchInput}
                        placeholder="Search"
                        placeholderTextColor="#999"
                    />
                    <TouchableOpacity>
                        <Mic size={20} color="#999" />
                    </TouchableOpacity>
                </View>
            </View>

            {/* Bottom Action Buttons */}
            <View style={styles.bottomActions}>
                <View style={styles.bottomButtonGroup}>
                    <TouchableOpacity 
                        style={styles.layersButton}
                        onPress={() => router.push('/(tabs)/jobs')}
                    >
                        <LayersDocumentIcon size={30} color={Colors.palette.inkBlack} />
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.profileButton}>
                        <View style={styles.profileIconContainer}>
                            <User size={24} color={Colors.palette.white} />
                        </View>
                    </TouchableOpacity>
                </View>
                <TouchableOpacity style={styles.addButton}>
                    <View style={styles.addButtonInner}>
                        <Plus size={32} color={Colors.palette.white} />
                    </View>
                </TouchableOpacity>
            </View>
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
        paddingHorizontal: 24,
        paddingTop: 8,
        paddingBottom: 16,
    },
    notificationButton: {
        position: 'relative',
    },
    badge: {
        position: 'absolute',
        top: -4,
        right: -4,
        backgroundColor: '#FF6B00', // Orange badge color
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
        paddingHorizontal: 24,
        marginBottom: 24,
    },
    greetingTitle: {
        fontSize: 32, // Large title
        fontWeight: '600',
        color: '#999', // Grey for first line based on image
        marginBottom: 4,
    },
    greetingSubtitle: {
        fontSize: 32,
        fontWeight: 'bold',
        color: Colors.palette.white,
        lineHeight: 38,
    },
    gridContainer: {
        flex: 1,
        paddingHorizontal: 24,
        gap: 12,
        marginBottom: 20,
        justifyContent: 'flex-end',
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
        borderRadius: 28, // Fully rounded
        paddingHorizontal: 20,
        gap: 12,
        borderWidth: 1,
        borderColor: 'rgba(255, 255, 255, 0.05)',
    },
    searchInput: {
        flex: 1,
        color: Colors.palette.white,
        fontSize: 16,
        height: '100%',
    },
    bottomActions: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 24,
        paddingBottom: 16,
    },
    bottomButtonGroup: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 40,
        paddingVertical: 8,
        paddingHorizontal: 8,
        gap: 8,
        borderWidth: 0,
        borderColor: Colors.palette.white,
    },
    layersButton: {
        width: 60,
        height: 60,
        borderRadius: 40,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: Colors.palette.white,
    },
    profileButton: {
        width: 60,
        height: 60,
        borderRadius: 40,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(255, 255, 255, 0.05)',
    },
    profileIconContainer: {
        width: 44,
        height: 44,
        borderRadius: 26,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 2,
        borderColor: Colors.palette.white,
    },
    addButton: {
        width: 70,
        height: 70,
        borderRadius: 40,
        backgroundColor: Colors.palette.shadowGrey,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 0,
        borderColor: Colors.palette.white,
    },
    addButtonInner: {
        width: 44,
        height: 44,
        borderRadius: 26,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: Colors.palette.white,
    },
});
