import React from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, Animated, Keyboard, ScrollView, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Bell, Search, Mic, User, CheckCircle, Clock, XCircle, FileText } from 'lucide-react-native';
import { useQuery } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import ActionCard from '../../components/ui/ActionCard';
import ScanIcon from '../../components/ui/icons/ScanIcon';
import CustomExportIcon from '../../components/ui/icons/CustomExportIcon';
import ExportIcon from '../../components/ui/icons/ExportIcon';
import RythmiqLogoIcon from '../../components/ui/icons/RythmiqLogoIcon';
import NotificationsPanel from '../../components/ui/NotificationsPanel';
import DocumentViewerModal from '../../components/ui/DocumentViewerModal';
import { router } from 'expo-router';
import { useAuth } from '../../contexts/AuthContext';
import { isDevSandboxMode, documentsApi, JobStatus } from '../../services/api';

type JobStatusType = 'pending' | 'processing' | 'completed' | 'failed';

const STATUS_CONFIG: Record<JobStatusType, { color: string; label: string }> = {
    pending:    { color: Colors.palette.amber, label: 'Pending' },
    processing: { color: '#89C7FE',            label: 'Processing' },
    completed:  { color: Colors.palette.green, label: 'Completed' },
    failed:     { color: Colors.palette.red,   label: 'Failed' },
};

function matchesQuery(job: JobStatus, q: string): boolean {
    const lower = q.toLowerCase();
    return (
        (job.document_type ?? '').toLowerCase().includes(lower) ||
        (job.document_category ?? '').toLowerCase().includes(lower) ||
        (job.document_subtype ?? '').toLowerCase().includes(lower) ||
        (job.document_name ?? '').toLowerCase().includes(lower) ||
        job.job_id.toLowerCase().includes(lower)
    );
}

function SearchResultCard({ job, onPress }: { job: JobStatus; onPress: () => void }) {
    const cfg = STATUS_CONFIG[job.status as JobStatusType] || STATUS_CONFIG.pending;
    const isActive = job.status === 'processing' || job.status === 'pending';
    const title = job.document_subtype || job.document_category || job.document_type || 'Document';
    const subtitle = job.document_type
        ? job.document_type.charAt(0).toUpperCase() + job.document_type.slice(1)
        : null;

    return (
        <TouchableOpacity style={searchStyles.card} onPress={onPress} activeOpacity={0.75}>
            <View style={[searchStyles.iconWrap, { backgroundColor: cfg.color + '18' }]}>
                {isActive
                    ? <ActivityIndicator size="small" color={cfg.color} />
                    : job.status === 'completed'
                        ? <CheckCircle size={20} color={cfg.color} />
                        : job.status === 'failed'
                            ? <XCircle size={20} color={cfg.color} />
                            : <Clock size={20} color={cfg.color} />
                }
            </View>
            <View style={searchStyles.cardInfo}>
                <Text style={searchStyles.cardTitle} numberOfLines={1}>{title}</Text>
                {subtitle && <Text style={searchStyles.cardSubtitle}>{subtitle}</Text>}
            </View>
            <View style={[searchStyles.statusPill, { backgroundColor: cfg.color + '18' }]}>
                <Text style={[searchStyles.statusText, { color: cfg.color }]}>{cfg.label}</Text>
            </View>
        </TouchableOpacity>
    );
}

export default function Dashboard() {
    const { user } = useAuth();
    const [notificationsPanelVisible, setNotificationsPanelVisible] = React.useState(false);
    const [unreadCount, setUnreadCount] = React.useState(0);
    const [isSearchFocused, setIsSearchFocused] = React.useState(false);
    const [searchQuery, setSearchQuery] = React.useState('');
    const [viewerJob, setViewerJob] = React.useState<JobStatus | null>(null);
    const overlayAnim = React.useRef(new Animated.Value(0)).current;
    const searchInputRef = React.useRef<TextInput>(null);

    const { data: jobsData } = useQuery({
        queryKey: ['jobs'],
        queryFn: documentsApi.listJobs,
        enabled: isSearchFocused,
        staleTime: 30000,
    });

    const searchResults = React.useMemo(() => {
        if (!searchQuery.trim() || !jobsData?.jobs) return [];
        return jobsData.jobs.filter(j => matchesQuery(j, searchQuery.trim()));
    }, [searchQuery, jobsData]);

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
        }).start(() => {
            setIsSearchFocused(false);
            setSearchQuery('');
        });
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
                        disabled
                        onPress={() => Alert.alert('Coming Soon', 'Custom Export is currently being worked on and will be available in a future update.')}
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
                        disabled
                        onPress={() => Alert.alert('Coming Soon', 'Concierge is currently being worked on and will be available in a future update.')}
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
                    {/* Animated search bar + results */}
                    <Animated.View
                        style={[
                            styles.searchOverlayContainer,
                            { opacity: overlayAnim, transform: [{ translateY: searchBarTranslateY }] },
                        ]}
                        onStartShouldSetResponder={() => true}
                    >
                        <View style={styles.searchOverlayBar}>
                            <Search size={20} color="#999" />
                            <TextInput
                                ref={searchInputRef}
                                style={styles.searchInput}
                                placeholder="Search documents…"
                                placeholderTextColor="#999"
                                value={searchQuery}
                                onChangeText={setSearchQuery}
                                autoCorrect={false}
                                autoCapitalize="none"
                            />
                            <TouchableOpacity onPress={closeSearch}>
                                <Text style={styles.cancelText}>Cancel</Text>
                            </TouchableOpacity>
                        </View>

                        {searchQuery.trim().length > 0 && (
                            <ScrollView
                                style={styles.resultsScroll}
                                keyboardShouldPersistTaps="handled"
                                showsVerticalScrollIndicator={false}
                            >
                                {searchResults.length === 0 ? (
                                    <View style={searchStyles.emptyRow}>
                                        <FileText size={20} color="#444" />
                                        <Text style={searchStyles.emptyText}>No documents found</Text>
                                    </View>
                                ) : (
                                    searchResults.map(job => (
                                        <SearchResultCard
                                            key={job.job_id}
                                            job={job}
                                            onPress={() => setViewerJob(job)}
                                        />
                                    ))
                                )}
                            </ScrollView>
                        )}
                    </Animated.View>
                </View>
            )}

            <NotificationsPanel
                visible={notificationsPanelVisible}
                onClose={() => setNotificationsPanelVisible(false)}
                onUnreadCountChange={setUnreadCount}
            />

            <DocumentViewerModal
                job={viewerJob}
                onClose={() => setViewerJob(null)}
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
    searchOverlayContainer: {
        position: 'absolute',
        top: 60,
        left: 24,
        right: 24,
        maxHeight: '80%',
    },
    searchOverlayBar: {
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
    resultsScroll: {
        marginTop: 10,
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.07)',
        maxHeight: 420,
    },
    cancelText: {
        color: '#999',
        fontSize: 14,
    },
});

const searchStyles = StyleSheet.create({
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 14,
        gap: 12,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(255,255,255,0.05)',
    },
    iconWrap: {
        width: 40,
        height: 40,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cardInfo: {
        flex: 1,
    },
    cardTitle: {
        fontSize: 14,
        fontWeight: '600',
        color: Colors.palette.white,
        marginBottom: 2,
    },
    cardSubtitle: {
        fontSize: 12,
        color: '#666',
        textTransform: 'capitalize',
    },
    statusPill: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 10,
    },
    statusText: {
        fontSize: 12,
        fontWeight: '600',
    },
    emptyRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        padding: 20,
        justifyContent: 'center',
    },
    emptyText: {
        color: '#555',
        fontSize: 14,
    },
});
