import React, { useMemo, useState } from 'react';
import {
    StyleSheet,
    Text,
    View,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    RefreshControl,
    Alert,
    Image,
    Modal,
    Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
    LogOut,
    ChevronRight,
    Bell,
    Shield,
    HelpCircle,
    Camera,
    PenLine,
    File,
    CheckCircle,
    Clock,
    XCircle,
    RefreshCw,
    Calendar,
    ArrowLeft,
    Download,
    Share2,
    X,
} from 'lucide-react-native';
import Colors from '../../constants/Colors';
import { useAuth } from '../../contexts/AuthContext';
import { documentsApi } from '../../services/api';
import type { JobStatus } from '../../services/api';
import { downloadJobOutput, shareFile, outputFormatToMime } from '../../services/download';
import NotificationsPanel from '../../components/ui/NotificationsPanel';

// ─── Document type display config ────────────────────────────────────────────

type DocTypeKey = 'photo' | 'signature' | 'document';

const DOC_TYPE_CONFIG: Record<DocTypeKey, { label: string; Icon: React.ComponentType<{ size: number; color: string }> }> = {
    photo: { label: 'Photo', Icon: Camera },
    signature: { label: 'Signature', Icon: PenLine },
    document: { label: 'Document', Icon: File },
};

// ─── Job status display config ────────────────────────────────────────────────

type StatusKey = 'pending' | 'processing' | 'completed' | 'failed';

const STATUS_CONFIG: Record<StatusKey, { color: string; label: string; Icon: React.ComponentType<{ size: number; color: string }> }> = {
    pending:    { color: Colors.palette.amber,  label: 'Pending',    Icon: Clock },
    processing: { color: '#5B8AF5',             label: 'Processing', Icon: RefreshCw },
    completed:  { color: Colors.palette.green,  label: 'Done',       Icon: CheckCircle },
    failed:     { color: Colors.palette.red,    label: 'Failed',     Icon: XCircle },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function AvatarBadge({ name, email }: { name?: string | null; email: string }) {
    const initials = useMemo(() => {
        if (name?.trim()) {
            return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
        }
        return email[0].toUpperCase();
    }, [name, email]);

    return (
        <View style={styles.avatarCircle}>
            <Text style={styles.avatarText}>{initials}</Text>
        </View>
    );
}

function SectionHeader({ title }: { title: string }) {
    return <Text style={styles.sectionHeader}>{title}</Text>;
}

function SettingsRow({
    Icon, label, onPress, destructive,
}: {
    Icon: React.ComponentType<{ size: number; color: string }>;
    label: string;
    onPress: () => void;
    destructive?: boolean;
}) {
    const color = destructive ? Colors.palette.red : Colors.palette.white;
    return (
        <TouchableOpacity style={styles.settingsRow} onPress={onPress} activeOpacity={0.7}>
            <View style={styles.settingsRowLeft}>
                <View style={[styles.settingsIcon, destructive && styles.settingsIconDestructive]}>
                    <Icon size={18} color={color} />
                </View>
                <Text style={[styles.settingsLabel, destructive && { color: Colors.palette.red }]}>
                    {label}
                </Text>
            </View>
            {!destructive && <ChevronRight size={18} color="rgba(255,255,255,0.3)" />}
        </TouchableOpacity>
    );
}

// ─── Document card (list row) ─────────────────────────────────────────────────

function DocumentCard({ job, onPress }: { job: JobStatus; onPress: () => void }) {
    const docKey = (job.document_type ?? 'document') as DocTypeKey;
    const statusKey = (job.status ?? 'pending') as StatusKey;
    const docConfig = DOC_TYPE_CONFIG[docKey] ?? DOC_TYPE_CONFIG.document;
    const statusConfig = STATUS_CONFIG[statusKey] ?? STATUS_CONFIG.pending;
    const { Icon: DocIcon } = docConfig;
    const { Icon: StatusIcon } = statusConfig;

    const [thumbError, setThumbError] = useState(false);
    const showThumb = !!job.preview_url && !thumbError;

    const displayName = job.document_name || docConfig.label;
    const dateStr = job.created_at
        ? new Date(job.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })
        : null;

    return (
        <TouchableOpacity style={styles.docCard} onPress={onPress} activeOpacity={0.75}>
            {/* Thumbnail or icon */}
            <View style={styles.docThumbWrap}>
                {showThumb ? (
                    <Image
                        source={{ uri: job.preview_url }}
                        style={styles.docThumb}
                        resizeMode="cover"
                        onError={() => setThumbError(true)}
                    />
                ) : (
                    <View style={styles.docThumbPlaceholder}>
                        <DocIcon size={26} color="rgba(255,255,255,0.3)" />
                    </View>
                )}
            </View>

            {/* Info */}
            <View style={styles.docInfo}>
                <Text style={styles.docName} numberOfLines={1}>{displayName}</Text>

                <View style={styles.docMeta}>
                    <Text style={styles.docMetaText}>{docConfig.label}</Text>
                    {dateStr && <Text style={styles.docMetaDot}>·</Text>}
                    {dateStr && <Text style={styles.docMetaText}>{dateStr}</Text>}
                    {job.quality_score != null && job.status === 'completed' && (
                        <>
                            <Text style={styles.docMetaDot}>·</Text>
                            <Text style={[styles.docMetaText, { color: Colors.palette.green }]}>
                                {Math.round(job.quality_score * 100)}%
                            </Text>
                        </>
                    )}
                </View>

                <View style={[styles.statusChip, { backgroundColor: `${statusConfig.color}22` }]}>
                    <StatusIcon size={10} color={statusConfig.color} />
                    <Text style={[styles.statusChipText, { color: statusConfig.color }]}>
                        {statusConfig.label}
                    </Text>
                </View>
            </View>
        </TouchableOpacity>
    );
}

// ─── Document detail modal ────────────────────────────────────────────────────

function DocumentDetailModal({ job, onClose }: { job: JobStatus; onClose: () => void }) {
    const [thumbError, setThumbError] = useState(false);
    const [downloading, setDownloading] = useState(false);

    const docKey = (job.document_type ?? 'document') as DocTypeKey;
    const statusKey = (job.status ?? 'pending') as StatusKey;
    const docConfig = DOC_TYPE_CONFIG[docKey] ?? DOC_TYPE_CONFIG.document;
    const statusConfig = STATUS_CONFIG[statusKey] ?? STATUS_CONFIG.pending;
    const { Icon: DocIcon } = docConfig;
    const { Icon: StatusIcon } = statusConfig;

    // Fetch full job detail to get download_url (only for completed jobs)
    const { data: detail, isLoading: detailLoading } = useQuery({
        queryKey: ['job', job.job_id],
        queryFn: () => documentsApi.getJobStatus(job.job_id),
        enabled: job.status === 'completed',
        staleTime: 300000,
    });

    const previewUrl = detail?.preview_url ?? job.preview_url;
    const displayName = job.document_name || docConfig.label;
    const qualityPct = job.quality_score != null ? Math.round(job.quality_score * 100) : null;

    const dateStr = job.created_at
        ? new Date(job.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
        : null;

    const handleDownload = async () => {
        // Prefer actual output file (JPEG/PDF), fall back to preview JPEG.
        // Never download the ZIP — users expect the actual image/document.
        const src = detail ?? job;
        const isEncrypted = src.output_encrypted === true;
        const downloadTarget =
            (!isEncrypted && src.output_url) ? src.output_url
            : src.preview_url                ? src.preview_url
            : null;

        if (!downloadTarget) {
            Alert.alert('File Not Ready', 'The processed file is not yet available. Please wait a moment and try again.');
            return;
        }

        const usingPreview = !(!isEncrypted && src.output_url) && !!src.preview_url;
        const { mimeType, ext } = outputFormatToMime(src.output_format);
        const fileExt  = usingPreview ? 'jpg' : ext;
        const fileMime = usingPreview ? 'image/jpeg' : mimeType;

        setDownloading(true);
        try {
            const result = await downloadJobOutput(job.job_id, downloadTarget, undefined, fileExt);
            if (result.success) {
                await shareFile(result.localPath, { mimeType: fileMime, dialogTitle: 'Save Document' });
            } else {
                Alert.alert('Download Failed', result.error || 'Could not download the document.');
            }
        } finally {
            setDownloading(false);
        }
    };

    const handleExport = () => {
        onClose();
        router.push({
            pathname: '/(tabs)/portal-selector',
            params: {
                documentId: job.job_id,
                documentCategory: job.document_category ?? '',
                documentSubtype: job.document_subtype ?? '',
                documentName: job.document_name ?? '',
            },
        });
    };

    return (
        <Modal visible animationType="slide" transparent onRequestClose={onClose}>
            {/* Backdrop */}
            <Pressable style={styles.modalBackdrop} onPress={onClose} />

            {/* Sheet */}
            <View style={styles.modalSheet}>
                {/* Handle bar */}
                <View style={styles.modalHandle} />

                {/* Close button */}
                <TouchableOpacity style={styles.modalCloseBtn} onPress={onClose} hitSlop={12}>
                    <X size={18} color="rgba(255,255,255,0.5)" />
                </TouchableOpacity>

                {/* Preview image */}
                {previewUrl && !thumbError ? (
                    <Image
                        source={{ uri: previewUrl }}
                        style={styles.modalPreview}
                        resizeMode="contain"
                        onError={() => setThumbError(true)}
                    />
                ) : (
                    <View style={styles.modalPreviewPlaceholder}>
                        <DocIcon size={52} color="rgba(255,255,255,0.15)" />
                    </View>
                )}

                {/* Document info */}
                <View style={styles.modalBody}>
                    {/* Name + badges */}
                    <Text style={styles.modalName} numberOfLines={2}>{displayName}</Text>

                    <View style={styles.modalBadgeRow}>
                        <View style={styles.typeBadge}>
                            <DocIcon size={12} color="rgba(255,255,255,0.55)" />
                            <Text style={styles.typeBadgeText}>{docConfig.label}</Text>
                        </View>
                        <View style={[styles.statusChip, { backgroundColor: `${statusConfig.color}22` }]}>
                            <StatusIcon size={10} color={statusConfig.color} />
                            <Text style={[styles.statusChipText, { color: statusConfig.color }]}>
                                {statusConfig.label}
                            </Text>
                        </View>
                    </View>

                    {/* Date */}
                    {dateStr && (
                        <View style={styles.modalInfoRow}>
                            <Calendar size={14} color="rgba(255,255,255,0.3)" />
                            <Text style={styles.modalInfoText}>{dateStr}</Text>
                        </View>
                    )}

                    {/* Quality score */}
                    {qualityPct != null && job.status === 'completed' && (
                        <View style={styles.qualityRow}>
                            <Text style={styles.qualityLabel}>Quality</Text>
                            <View style={styles.qualityBarBg}>
                                <View
                                    style={[
                                        styles.qualityBarFill,
                                        {
                                            width: `${qualityPct}%`,
                                            backgroundColor: qualityPct >= 80
                                                ? Colors.palette.green
                                                : qualityPct >= 60
                                                    ? Colors.palette.amber
                                                    : Colors.palette.red,
                                        },
                                    ]}
                                />
                            </View>
                            <Text style={styles.qualityPct}>{qualityPct}%</Text>
                        </View>
                    )}
                </View>

                {/* Action buttons */}
                {job.status === 'completed' && (
                    <View style={styles.modalActions}>
                        <TouchableOpacity
                            style={styles.btnSecondary}
                            onPress={handleDownload}
                            disabled={downloading || detailLoading}
                            activeOpacity={0.75}
                        >
                            {downloading
                                ? <ActivityIndicator size="small" color={Colors.palette.white} />
                                : <Download size={17} color={Colors.palette.white} />
                            }
                            <Text style={styles.btnSecondaryText}>
                                {downloading ? 'Saving…' : 'Download'}
                            </Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={styles.btnPrimary}
                            onPress={handleExport}
                            activeOpacity={0.85}
                        >
                            <Share2 size={17} color={Colors.palette.inkBlack} />
                            <Text style={styles.btnPrimaryText}>Export</Text>
                        </TouchableOpacity>
                    </View>
                )}
            </View>
        </Modal>
    );
}

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function ProfileScreen() {
    const { user, logout } = useAuth();
    const [selectedJob, setSelectedJob] = useState<JobStatus | null>(null);
    const [notificationsPanelVisible, setNotificationsPanelVisible] = useState(false);

    const { data, isLoading, refetch, isRefetching } = useQuery({
        queryKey: ['jobs'],
        queryFn: documentsApi.listJobs,
        // Only poll while jobs are actively processing; otherwise stop
        refetchInterval: (query) => {
            const jobs = (query.state.data as { jobs: JobStatus[] } | undefined)?.jobs ?? [];
            const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'processing');
            return hasActive ? 15000 : false;
        },
    });

    const jobs = useMemo(() => data?.jobs ?? [], [data]);

    const masterJobs = useMemo(
        () => jobs.filter((j) => !j.job_type || j.job_type === 'master'),
        [jobs]
    );

    const stats = useMemo(() => ({
        total: masterJobs.length,
        completed: masterJobs.filter((j) => j.status === 'completed').length,
        processing: masterJobs.filter((j) => j.status === 'processing' || j.status === 'pending').length,
        failed: masterJobs.filter((j) => j.status === 'failed').length,
    }), [masterJobs]);

    const memberSince = useMemo(() => {
        if (!user?.created_at) return null;
        return new Date(user.created_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });
    }, [user]);

    const handleLogout = () => {
        Alert.alert('Log Out', 'Are you sure you want to log out?', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Log Out',
                style: 'destructive',
                onPress: async () => {
                    await logout();
                    router.replace('/');
                },
            },
        ]);
    };

    return (
        <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
                    <ArrowLeft size={22} color={Colors.palette.white} />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Profile</Text>
                <View style={{ width: 38 }} />
            </View>

            <ScrollView
                showsVerticalScrollIndicator={false}
                refreshControl={
                    <RefreshControl
                        refreshing={isRefetching}
                        onRefresh={refetch}
                        tintColor={Colors.palette.white}
                    />
                }
                contentContainerStyle={styles.scrollContent}
            >
                {/* Profile Card */}
                <View style={styles.profileCard}>
                    <AvatarBadge name={user?.name} email={user?.email ?? ''} />
                    <View style={styles.profileInfo}>
                        {user?.name ? <Text style={styles.profileName}>{user.name}</Text> : null}
                        <Text style={styles.profileEmail}>{user?.email}</Text>
                        {memberSince && (
                            <View style={styles.memberRow}>
                                <Calendar size={12} color="rgba(255,255,255,0.35)" />
                                <Text style={styles.memberSince}>Member since {memberSince}</Text>
                            </View>
                        )}
                    </View>
                </View>

                {/* Stats Bar */}
                <View style={styles.statsBar}>
                    <View style={styles.statItem}>
                        <Text style={styles.statValue}>{stats.total}</Text>
                        <Text style={styles.statLabel}>Total</Text>
                    </View>
                    <View style={styles.statDivider} />
                    <View style={styles.statItem}>
                        <Text style={[styles.statValue, { color: Colors.palette.green }]}>{stats.completed}</Text>
                        <Text style={styles.statLabel}>Done</Text>
                    </View>
                    <View style={styles.statDivider} />
                    <View style={styles.statItem}>
                        <Text style={[styles.statValue, { color: Colors.palette.amber }]}>{stats.processing}</Text>
                        <Text style={styles.statLabel}>Pending</Text>
                    </View>
                    {stats.failed > 0 && (
                        <>
                            <View style={styles.statDivider} />
                            <View style={styles.statItem}>
                                <Text style={[styles.statValue, { color: Colors.palette.red }]}>{stats.failed}</Text>
                                <Text style={styles.statLabel}>Failed</Text>
                            </View>
                        </>
                    )}
                </View>

                {/* Account Settings */}
                <SectionHeader title="Account" />
                <View style={styles.settingsGroup}>
                    <SettingsRow Icon={Bell}       label="Notifications"    onPress={() => setNotificationsPanelVisible(true)} />
                    <View style={styles.rowDivider} />
                    <SettingsRow Icon={Shield}     label="Security & Privacy" onPress={() => {}} />
                    <View style={styles.rowDivider} />
                    <SettingsRow Icon={HelpCircle} label="Help & Support"   onPress={() => {}} />
                </View>
                <View style={styles.settingsGroup}>
                    <SettingsRow Icon={LogOut} label="Log Out" onPress={handleLogout} destructive />
                </View>

                {/* My Documents */}
                <SectionHeader title="My Documents" />

                {isLoading ? (
                    <View style={styles.loadingWrap}>
                        <ActivityIndicator size="small" color={Colors.palette.white} />
                        <Text style={styles.loadingText}>Loading documents…</Text>
                    </View>
                ) : masterJobs.length === 0 ? (
                    <View style={styles.emptyWrap}>
                        <File size={40} color="rgba(255,255,255,0.2)" />
                        <Text style={styles.emptyText}>No documents yet</Text>
                        <TouchableOpacity
                            style={styles.emptyAction}
                            onPress={() => router.push('/(tabs)/capture')}
                        >
                            <Text style={styles.emptyActionText}>Scan a document</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <View style={styles.docList}>
                        {masterJobs.map((job) => (
                            <DocumentCard
                                key={job.job_id}
                                job={job}
                                onPress={() => setSelectedJob(job)}
                            />
                        ))}
                    </View>
                )}

                <View style={{ height: 32 }} />
            </ScrollView>

            <NotificationsPanel
                visible={notificationsPanelVisible}
                onClose={() => setNotificationsPanelVisible(false)}
            />

            {/* Document detail modal */}
            {selectedJob && (
                <DocumentDetailModal
                    job={selectedJob}
                    onClose={() => setSelectedJob(null)}
                />
            )}
        </SafeAreaView>
    );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: Colors.palette.inkBlack,
    },
    // Header
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingTop: 8,
        paddingBottom: 16,
    },
    backButton: {
        width: 38,
        height: 38,
        borderRadius: 19,
        backgroundColor: Colors.palette.shadowGrey,
        alignItems: 'center',
        justifyContent: 'center',
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '600',
        color: Colors.palette.white,
    },
    scrollContent: {
        paddingHorizontal: 20,
    },
    // Profile card
    profileCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 20,
        padding: 20,
        marginBottom: 12,
        gap: 16,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
    },
    avatarCircle: {
        width: 64,
        height: 64,
        borderRadius: 32,
        backgroundColor: 'rgba(255,255,255,0.08)',
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1.5,
        borderColor: 'rgba(255,255,255,0.12)',
    },
    avatarText: {
        fontSize: 24,
        fontWeight: '700',
        color: Colors.palette.white,
        letterSpacing: 1,
    },
    profileInfo: {
        flex: 1,
        gap: 3,
    },
    profileName: {
        fontSize: 18,
        fontWeight: '700',
        color: Colors.palette.white,
    },
    profileEmail: {
        fontSize: 13,
        color: 'rgba(255,255,255,0.5)',
    },
    memberRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        marginTop: 4,
    },
    memberSince: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.3)',
    },
    // Stats bar
    statsBar: {
        flexDirection: 'row',
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 16,
        paddingVertical: 16,
        paddingHorizontal: 12,
        marginBottom: 24,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
    },
    statItem: {
        flex: 1,
        alignItems: 'center',
        gap: 4,
    },
    statValue: {
        fontSize: 22,
        fontWeight: '700',
        color: Colors.palette.white,
    },
    statLabel: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.4)',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    statDivider: {
        width: 1,
        backgroundColor: 'rgba(255,255,255,0.07)',
        marginHorizontal: 4,
    },
    // Section header
    sectionHeader: {
        fontSize: 12,
        fontWeight: '600',
        color: 'rgba(255,255,255,0.4)',
        textTransform: 'uppercase',
        letterSpacing: 1,
        marginBottom: 10,
    },
    // Settings
    settingsGroup: {
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 16,
        marginBottom: 16,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
    },
    settingsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: 14,
        paddingHorizontal: 16,
    },
    settingsRowLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
    },
    settingsIcon: {
        width: 32,
        height: 32,
        borderRadius: 8,
        backgroundColor: 'rgba(255,255,255,0.07)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    settingsIconDestructive: {
        backgroundColor: `${Colors.palette.red}22`,
    },
    settingsLabel: {
        fontSize: 15,
        color: Colors.palette.white,
        fontWeight: '500',
    },
    rowDivider: {
        height: 1,
        backgroundColor: 'rgba(255,255,255,0.05)',
        marginHorizontal: 16,
    },
    // Document list
    docList: {
        gap: 10,
    },
    docCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 16,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
        gap: 14,
        paddingLeft: 12,
        paddingRight: 16,
        paddingVertical: 12,
    },
    docThumbWrap: {
        width: 88,
        height: 88,
        flexShrink: 0,
        borderRadius: 12,
        overflow: 'hidden',
    },
    docThumb: {
        width: '100%',
        height: '100%',
    },
    docThumbPlaceholder: {
        width: '100%',
        height: '100%',
        backgroundColor: 'rgba(255,255,255,0.04)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    docInfo: {
        flex: 1,
        gap: 5,
    },
    docName: {
        fontSize: 14,
        fontWeight: '600',
        color: Colors.palette.white,
    },
    docMeta: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 5,
        flexWrap: 'wrap',
    },
    docMetaText: {
        fontSize: 12,
        color: 'rgba(255,255,255,0.4)',
    },
    docMetaDot: {
        fontSize: 12,
        color: 'rgba(255,255,255,0.2)',
    },
    statusChip: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 20,
        alignSelf: 'flex-start',
    },
    statusChipText: {
        fontSize: 11,
        fontWeight: '600',
    },
    // Loading / Empty
    loadingWrap: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingVertical: 32,
        justifyContent: 'center',
    },
    loadingText: {
        color: 'rgba(255,255,255,0.4)',
        fontSize: 14,
    },
    emptyWrap: {
        alignItems: 'center',
        paddingVertical: 40,
        gap: 12,
    },
    emptyText: {
        color: 'rgba(255,255,255,0.3)',
        fontSize: 15,
    },
    emptyAction: {
        paddingHorizontal: 20,
        paddingVertical: 10,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.15)',
        marginTop: 4,
    },
    emptyActionText: {
        color: Colors.palette.white,
        fontSize: 14,
        fontWeight: '500',
    },
    // Modal
    modalBackdrop: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.65)',
    },
    modalSheet: {
        backgroundColor: '#1A1A2E',
        borderTopLeftRadius: 28,
        borderTopRightRadius: 28,
        paddingBottom: 36,
        borderTopWidth: 1,
        borderColor: 'rgba(255,255,255,0.07)',
    },
    modalHandle: {
        width: 36,
        height: 4,
        borderRadius: 2,
        backgroundColor: 'rgba(255,255,255,0.18)',
        alignSelf: 'center',
        marginTop: 12,
        marginBottom: 4,
    },
    modalCloseBtn: {
        position: 'absolute',
        top: 16,
        right: 18,
        padding: 6,
        zIndex: 10,
    },
    modalPreview: {
        width: '100%',
        height: 220,
        backgroundColor: 'rgba(0,0,0,0.4)',
        marginTop: 8,
    },
    modalPreviewPlaceholder: {
        width: '100%',
        height: 180,
        backgroundColor: 'rgba(255,255,255,0.03)',
        alignItems: 'center',
        justifyContent: 'center',
        marginTop: 8,
    },
    modalBody: {
        paddingHorizontal: 22,
        paddingTop: 18,
        gap: 10,
    },
    modalName: {
        fontSize: 17,
        fontWeight: '700',
        color: Colors.palette.white,
    },
    modalBadgeRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    typeBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 5,
        paddingHorizontal: 9,
        paddingVertical: 4,
        borderRadius: 20,
        backgroundColor: 'rgba(255,255,255,0.07)',
        alignSelf: 'flex-start',
    },
    typeBadgeText: {
        fontSize: 12,
        color: 'rgba(255,255,255,0.55)',
        fontWeight: '500',
    },
    modalInfoRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 7,
    },
    modalInfoText: {
        fontSize: 13,
        color: 'rgba(255,255,255,0.4)',
    },
    qualityRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        marginTop: 2,
    },
    qualityLabel: {
        fontSize: 13,
        color: 'rgba(255,255,255,0.4)',
        width: 52,
    },
    qualityBarBg: {
        flex: 1,
        height: 6,
        borderRadius: 3,
        backgroundColor: 'rgba(255,255,255,0.08)',
        overflow: 'hidden',
    },
    qualityBarFill: {
        height: '100%',
        borderRadius: 3,
    },
    qualityPct: {
        fontSize: 13,
        fontWeight: '600',
        color: Colors.palette.white,
        width: 36,
        textAlign: 'right',
    },
    // Modal action buttons
    modalActions: {
        flexDirection: 'row',
        paddingHorizontal: 22,
        paddingTop: 20,
        gap: 12,
    },
    btnSecondary: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 14,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.15)',
        backgroundColor: 'rgba(255,255,255,0.05)',
    },
    btnSecondaryText: {
        fontSize: 15,
        fontWeight: '600',
        color: Colors.palette.white,
    },
    btnPrimary: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 14,
        borderRadius: 16,
        backgroundColor: Colors.palette.white,
    },
    btnPrimaryText: {
        fontSize: 15,
        fontWeight: '700',
        color: Colors.palette.inkBlack,
    },
});
