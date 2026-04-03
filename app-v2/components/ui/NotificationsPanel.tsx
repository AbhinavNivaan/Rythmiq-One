/**
 * NotificationsPanel
 *
 * A slide-up modal panel accessible from the Bell icon in the Dashboard header.
 * Contains two tabs:
 *   1. Notifications – derived from recent job events (completed / failed)
 *   2. Jobs          – real jobs fetched from the API
 *
 * Tapping a notification opens a detail modal and marks it as read.
 * The panel reports the live unread count to the parent via onUnreadCountChange.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    Animated,
    Modal,
    PanResponder,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    TouchableWithoutFeedback,
    View,
    Dimensions,
    ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import {
    Bell,
    BriefcaseBusiness,
    FileCheck,
    FileWarning,
    Layers,
    X,
    CheckCircle,
    AlertCircle,
} from 'lucide-react-native';
import { Ionicons } from '@expo/vector-icons';
import Colors from '../../constants/Colors';
import { documentsApi, JobStatus } from '../../services/api';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

type TabId = 'notifications' | 'jobs';

interface DerivedNotification {
    id: string;
    isWarning: boolean;
    title: string;
    body: string;
    timestamp: string;
    isNew: boolean;
    jobId: string;
    jobStatus: JobStatus['status'];
    documentName: string;
    documentType: string;
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function relativeTime(isoString?: string | null): string {
    if (!isoString) return '';
    const diff = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hr ago`;
    const days = Math.floor(hrs / 24);
    if (days === 1) return 'Yesterday';
    return `${days} days ago`;
}

function shortId(fullId: string): string {
    return fullId.replace(/-/g, '').slice(0, 8);
}

function jobToNotification(job: JobStatus): DerivedNotification | null {
    if (job.status !== 'completed' && job.status !== 'failed') return null;

    const docName = job.document_name
        ? job.document_name.replace(/\.[^/.]+$/, '')
        : job.document_type ?? 'Document';
    const docType = job.document_type ?? 'document';

    const ageMs = job.created_at ? Date.now() - new Date(job.created_at).getTime() : Infinity;
    const isNew = ageMs < 24 * 60 * 60 * 1000;

    if (job.status === 'completed') {
        return {
            id: job.job_id,
            isWarning: false,
            title: 'Document processed',
            body: `"${docName}" has been processed successfully.`,
            timestamp: relativeTime(job.created_at),
            isNew,
            jobId: job.job_id,
            jobStatus: job.status,
            documentName: docName,
            documentType: docType,
        };
    }

    return {
        id: job.job_id,
        isWarning: true,
        title: 'Processing failed',
        body: job.error?.message
            ? `"${docName}" failed: ${job.error.message}`
            : `"${docName}" could not be processed. Please try again.`,
        timestamp: relativeTime(job.created_at),
        isNew,
        jobId: job.job_id,
        jobStatus: job.status,
        documentName: docName,
        documentType: docType,
    };
}

// ─────────────────────────────────────────────────────────────
// Notification Detail Modal
// ─────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<JobStatus['status'], string> = {
    pending: 'Pending',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
};

const STATUS_COLOR: Record<JobStatus['status'], string> = {
    pending: Colors.palette.amber,
    processing: Colors.palette.white,
    completed: Colors.palette.green,
    failed: Colors.palette.red,
};

interface DetailModalProps {
    notification: DerivedNotification | null;
    onClose: () => void;
}

function NotificationDetailModal({ notification, onClose }: DetailModalProps) {
    const scaleAnim = useRef(new Animated.Value(0.88)).current;
    const opacityAnim = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        if (notification) {
            Animated.parallel([
                Animated.spring(scaleAnim, {
                    toValue: 1,
                    useNativeDriver: true,
                    damping: 18,
                    stiffness: 220,
                }),
                Animated.timing(opacityAnim, {
                    toValue: 1,
                    duration: 180,
                    useNativeDriver: true,
                }),
            ]).start();
        } else {
            scaleAnim.setValue(0.88);
            opacityAnim.setValue(0);
        }
    }, [notification]);

    if (!notification) return null;

    const statusColor = STATUS_COLOR[notification.jobStatus];
    const statusLabel = STATUS_LABEL[notification.jobStatus];

    return (
        <Modal
            visible={!!notification}
            transparent
            animationType="none"
            statusBarTranslucent
            onRequestClose={onClose}
        >
            {/* Backdrop */}
            <TouchableWithoutFeedback onPress={onClose}>
                <Animated.View style={[detailStyles.backdrop, { opacity: opacityAnim }]} />
            </TouchableWithoutFeedback>

            {/* Card */}
            <View style={detailStyles.centeredWrap} pointerEvents="box-none">
                <Animated.View
                    style={[
                        detailStyles.card,
                        { opacity: opacityAnim, transform: [{ scale: scaleAnim }] },
                    ]}
                >
                    {/* Header row */}
                    <View style={detailStyles.headerRow}>
                        <View style={[
                            detailStyles.iconWrap,
                            { backgroundColor: notification.isWarning ? 'rgba(255,160,0,0.12)' : 'rgba(60,220,110,0.12)' },
                        ]}>
                            {notification.isWarning
                                ? <AlertCircle size={22} color={Colors.palette.amber} />
                                : <CheckCircle size={22} color={Colors.palette.green} />
                            }
                        </View>
                        <TouchableOpacity style={detailStyles.closeBtn} onPress={onClose}>
                            <X size={18} color="rgba(255,255,255,0.45)" />
                        </TouchableOpacity>
                    </View>

                    {/* Title */}
                    <Text style={detailStyles.title}>{notification.title}</Text>

                    {/* Body */}
                    <Text style={detailStyles.body}>{notification.body}</Text>

                    {/* Metadata rows */}
                    <View style={detailStyles.metaBlock}>
                        <View style={detailStyles.metaRow}>
                            <Text style={detailStyles.metaLabel}>Document</Text>
                            <Text style={detailStyles.metaValue} numberOfLines={1}>
                                {notification.documentName}
                            </Text>
                        </View>
                        <View style={detailStyles.metaDivider} />
                        <View style={detailStyles.metaRow}>
                            <Text style={detailStyles.metaLabel}>Status</Text>
                            <Text style={[detailStyles.metaValue, { color: statusColor }]}>
                                {statusLabel}
                            </Text>
                        </View>
                        <View style={detailStyles.metaDivider} />
                        <View style={detailStyles.metaRow}>
                            <Text style={detailStyles.metaLabel}>Job ID</Text>
                            <Text style={[detailStyles.metaValue, detailStyles.monoValue]}>
                                #{shortId(notification.jobId)}
                            </Text>
                        </View>
                        <View style={detailStyles.metaDivider} />
                        <View style={detailStyles.metaRow}>
                            <Text style={detailStyles.metaLabel}>Time</Text>
                            <Text style={detailStyles.metaValue}>{notification.timestamp}</Text>
                        </View>
                    </View>

                    {/* Dismiss button */}
                    <TouchableOpacity style={detailStyles.dismissBtn} onPress={onClose} activeOpacity={0.8}>
                        <Text style={detailStyles.dismissText}>Got it</Text>
                    </TouchableOpacity>
                </Animated.View>
            </View>
        </Modal>
    );
}

// ─────────────────────────────────────────────────────────────
// Notification Card
// ─────────────────────────────────────────────────────────────

interface NotificationCardProps {
    item: DerivedNotification;
    isRead: boolean;
    onPress: (item: DerivedNotification) => void;
}

function NotificationCard({ item, isRead, onPress }: NotificationCardProps) {
    const icon = item.isWarning
        ? <FileWarning size={20} color={Colors.palette.amber} />
        : <FileCheck size={20} color={Colors.palette.white} />;

    return (
        <TouchableOpacity
            style={[notifStyles.card, isRead && notifStyles.cardRead]}
            onPress={() => onPress(item)}
            activeOpacity={0.75}
        >
            <View style={notifStyles.iconWrap}>{icon}</View>
            <View style={notifStyles.content}>
                <View style={notifStyles.titleRow}>
                    <Text style={notifStyles.title} numberOfLines={1}>
                        {item.title}
                    </Text>
                    {!isRead && item.isNew && <View style={notifStyles.unreadDot} />}
                </View>
                <Text style={notifStyles.body} numberOfLines={2}>
                    {item.body}
                </Text>
                <Text style={notifStyles.timestamp}>{item.timestamp}</Text>
            </View>
        </TouchableOpacity>
    );
}

// ─────────────────────────────────────────────────────────────
// Job Row
// ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
    pending: { icon: 'time-outline' as const, color: Colors.palette.amber, label: 'Pending' },
    processing: { icon: 'sync-outline' as const, color: Colors.palette.white, label: 'Processing' },
    completed: { icon: 'checkmark-circle' as const, color: Colors.palette.green, label: 'Completed' },
    failed: { icon: 'close-circle' as const, color: Colors.palette.red, label: 'Failed' },
};

function JobRow({ job }: { job: JobStatus }) {
    const cfg = STATUS_CONFIG[job.status];
    const isProcessing = job.status === 'processing';
    const id = shortId(job.job_id);

    return (
        <TouchableOpacity
            style={jobStyles.row}
            activeOpacity={0.75}
            onPress={() => router.push({ pathname: '/(tabs)/job-detail', params: { jobId: job.job_id } } as any)}
        >
            <View style={jobStyles.iconWrap}>
                {isProcessing ? (
                    <ActivityIndicator size="small" color={cfg.color} />
                ) : (
                    <Ionicons name={cfg.icon} size={20} color={cfg.color} />
                )}
            </View>
            <View style={jobStyles.info}>
                <Text style={jobStyles.jobId}>Job #{id}</Text>
                <Text style={[jobStyles.status, { color: cfg.color }]}>
                    {cfg.label}
                    {job.quality_score != null && job.status === 'completed'
                        ? `  ·  Quality ${Math.round(job.quality_score * 100)}%`
                        : ''}
                </Text>
            </View>
            <View style={jobStyles.meta}>
                <Text style={jobStyles.time}>{relativeTime(job.created_at)}</Text>
                <Ionicons name="chevron-forward-outline" size={16} color="rgba(255,255,255,0.3)" />
            </View>
        </TouchableOpacity>
    );
}

function EmptyState({ message }: { message: string }) {
    return (
        <View style={emptyStyles.wrap}>
            <Text style={emptyStyles.text}>{message}</Text>
        </View>
    );
}

// ─────────────────────────────────────────────────────────────
// Main panel
// ─────────────────────────────────────────────────────────────

const SCREEN_HEIGHT = Dimensions.get('window').height;
const PANEL_HEIGHT = SCREEN_HEIGHT * 0.78;

interface NotificationsPanelProps {
    visible: boolean;
    onClose: () => void;
    onUnreadCountChange?: (count: number) => void;
}

export default function NotificationsPanel({
    visible,
    onClose,
    onUnreadCountChange,
}: NotificationsPanelProps) {
    const [activeTab, setActiveTab] = useState<TabId>('notifications');
    const [jobs, setJobs] = useState<JobStatus[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [readIds, setReadIds] = useState<Set<string>>(new Set());
    const [selectedNotification, setSelectedNotification] = useState<DerivedNotification | null>(null);

    const slideAnim = useRef(new Animated.Value(PANEL_HEIGHT)).current;
    const backdropOpacity = useRef(new Animated.Value(0)).current;

    // ── data fetching ──────────────────────────────────────
    const fetchJobs = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const { jobs: fetched } = await documentsApi.listJobs();
            setJobs(fetched);
        } catch (e: any) {
            setError(e?.message ?? 'Could not load jobs');
        } finally {
            setLoading(false);
        }
    }, []);

    // Background fetch on mount to seed the badge count
    useEffect(() => {
        fetchJobs();
    }, []);

    // ── derived data ───────────────────────────────────────
    const notifications: DerivedNotification[] = jobs
        .map(jobToNotification)
        .filter((n): n is DerivedNotification => n !== null)
        .slice(0, 20);

    const unreadCount = notifications.filter((n) => n.isNew && !readIds.has(n.id)).length;

    // Report unread count to parent whenever it changes
    useEffect(() => {
        onUnreadCountChange?.(unreadCount);
    }, [unreadCount, onUnreadCountChange]);

    // ── mark as read ───────────────────────────────────────
    const handleNotificationPress = useCallback((item: DerivedNotification) => {
        setSelectedNotification(item);
    }, []);

    const handleDetailClose = useCallback(() => {
        if (selectedNotification) {
            setReadIds((prev) => new Set(prev).add(selectedNotification.id));
        }
        setSelectedNotification(null);
    }, [selectedNotification]);

    // ── animation helpers ──────────────────────────────────
    const openPanel = () => {
        Animated.parallel([
            Animated.spring(slideAnim, {
                toValue: 0,
                useNativeDriver: true,
                damping: 20,
                stiffness: 200,
            }),
            Animated.timing(backdropOpacity, {
                toValue: 1,
                duration: 250,
                useNativeDriver: true,
            }),
        ]).start();
    };

    const closePanel = (callback?: () => void) => {
        Animated.parallel([
            Animated.timing(slideAnim, {
                toValue: PANEL_HEIGHT,
                duration: 280,
                useNativeDriver: true,
            }),
            Animated.timing(backdropOpacity, {
                toValue: 0,
                duration: 250,
                useNativeDriver: true,
            }),
        ]).start(() => callback?.());
    };

    useEffect(() => {
        if (visible) {
            openPanel();
            fetchJobs();
        }
    }, [visible]);

    const handleClose = () => closePanel(onClose);

    // ── drag-to-dismiss ────────────────────────────────────
    const panResponder = useRef(
        PanResponder.create({
            onStartShouldSetPanResponder: () => true,
            onMoveShouldSetPanResponder: (_, gs) => gs.dy > 5,
            onPanResponderMove: (_, gs) => {
                if (gs.dy > 0) slideAnim.setValue(gs.dy);
            },
            onPanResponderRelease: (_, gs) => {
                if (gs.dy > PANEL_HEIGHT * 0.25 || gs.vy > 0.5) {
                    closePanel(onClose);
                } else {
                    Animated.spring(slideAnim, {
                        toValue: 0,
                        useNativeDriver: true,
                        damping: 20,
                        stiffness: 200,
                    }).start();
                }
            },
        })
    ).current;

    const newNotifications = notifications.filter((n) => n.isNew && !readIds.has(n.id));
    const earlierNotifications = notifications.filter((n) => !n.isNew || readIds.has(n.id));

    const jobStats = {
        completed: jobs.filter((j) => j.status === 'completed').length,
        processing: jobs.filter((j) => j.status === 'processing').length,
        pending: jobs.filter((j) => j.status === 'pending').length,
    };

    return (
        <>
            <Modal
                visible={visible}
                transparent
                animationType="none"
                statusBarTranslucent
                onRequestClose={handleClose}
            >
                {/* Backdrop */}
                <TouchableWithoutFeedback onPress={handleClose}>
                    <Animated.View style={[styles.backdrop, { opacity: backdropOpacity }]} />
                </TouchableWithoutFeedback>

                {/* Slide-up panel */}
                <Animated.View style={[styles.panel, { transform: [{ translateY: slideAnim }] }]}>
                    {/* Drag handle */}
                    <View {...panResponder.panHandlers} style={styles.dragArea}>
                        <View style={styles.handle} />
                    </View>

                    {/* Panel header */}
                    <View style={styles.panelHeader}>
                        <View style={styles.panelTitleRow}>
                            <Bell size={18} color={Colors.palette.white} />
                            <Text style={styles.panelTitle}>Notifications</Text>
                            {unreadCount > 0 && (
                                <View style={styles.unreadBadge}>
                                    <Text style={styles.unreadBadgeText}>{unreadCount}</Text>
                                </View>
                            )}
                        </View>
                        <TouchableOpacity onPress={handleClose} style={styles.closeButton}>
                            <X size={20} color="rgba(255,255,255,0.5)" />
                        </TouchableOpacity>
                    </View>

                    {/* Toggle tabs */}
                    <View style={styles.tabRow}>
                        <TouchableOpacity
                            style={[styles.tabPill, activeTab === 'notifications' && styles.tabPillActive]}
                            onPress={() => setActiveTab('notifications')}
                            activeOpacity={0.8}
                        >
                            <Bell
                                size={14}
                                color={activeTab === 'notifications' ? Colors.palette.inkBlack : 'rgba(255,255,255,0.5)'}
                            />
                            <Text
                                style={[
                                    styles.tabPillText,
                                    activeTab === 'notifications' && styles.tabPillTextActive,
                                ]}
                            >
                                Notifications
                            </Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={[styles.tabPill, activeTab === 'jobs' && styles.tabPillActive]}
                            onPress={() => setActiveTab('jobs')}
                            activeOpacity={0.8}
                        >
                            <BriefcaseBusiness
                                size={14}
                                color={activeTab === 'jobs' ? Colors.palette.inkBlack : 'rgba(255,255,255,0.5)'}
                            />
                            <Text
                                style={[
                                    styles.tabPillText,
                                    activeTab === 'jobs' && styles.tabPillTextActive,
                                ]}
                            >
                                Jobs
                            </Text>
                        </TouchableOpacity>
                    </View>

                    {/* ── NOTIFICATIONS TAB ── */}
                    {activeTab === 'notifications' && (
                        <ScrollView
                            style={styles.scrollArea}
                            contentContainerStyle={styles.scrollContent}
                            showsVerticalScrollIndicator={false}
                        >
                            {loading ? (
                                <ActivityIndicator
                                    size="small"
                                    color="rgba(255,255,255,0.4)"
                                    style={{ marginTop: 32 }}
                                />
                            ) : error ? (
                                <EmptyState message={error} />
                            ) : notifications.length === 0 ? (
                                <EmptyState message="No notifications yet" />
                            ) : (
                                <>
                                    {newNotifications.length > 0 && (
                                        <>
                                            <Text style={styles.sectionLabel}>New</Text>
                                            {newNotifications.map((n) => (
                                                <NotificationCard
                                                    key={n.id}
                                                    item={n}
                                                    isRead={readIds.has(n.id)}
                                                    onPress={handleNotificationPress}
                                                />
                                            ))}
                                        </>
                                    )}
                                    {earlierNotifications.length > 0 && (
                                        <>
                                            <Text style={[styles.sectionLabel, newNotifications.length > 0 && { marginTop: 20 }]}>
                                                Earlier
                                            </Text>
                                            {earlierNotifications.map((n) => (
                                                <NotificationCard
                                                    key={n.id}
                                                    item={n}
                                                    isRead={readIds.has(n.id)}
                                                    onPress={handleNotificationPress}
                                                />
                                            ))}
                                        </>
                                    )}
                                    <Text style={styles.endNote}>You're all caught up</Text>
                                </>
                            )}
                        </ScrollView>
                    )}

                    {/* ── JOBS TAB ── */}
                    {activeTab === 'jobs' && (
                        <>
                            {/* Stats strip */}
                            <View style={styles.jobStatsRow}>
                                <View style={styles.jobStat}>
                                    <Text style={[styles.jobStatValue, { color: Colors.palette.green }]}>
                                        {jobStats.completed}
                                    </Text>
                                    <Text style={styles.jobStatLabel}>Completed</Text>
                                </View>
                                <View style={styles.jobStatDivider} />
                                <View style={styles.jobStat}>
                                    <Text style={[styles.jobStatValue, { color: Colors.palette.white }]}>
                                        {jobStats.processing}
                                    </Text>
                                    <Text style={styles.jobStatLabel}>Processing</Text>
                                </View>
                                <View style={styles.jobStatDivider} />
                                <View style={styles.jobStat}>
                                    <Text style={[styles.jobStatValue, { color: Colors.palette.amber }]}>
                                        {jobStats.pending}
                                    </Text>
                                    <Text style={styles.jobStatLabel}>Pending</Text>
                                </View>
                            </View>

                            <ScrollView
                                style={styles.scrollArea}
                                contentContainerStyle={styles.scrollContent}
                                showsVerticalScrollIndicator={false}
                            >
                                {loading ? (
                                    <ActivityIndicator
                                        size="small"
                                        color="rgba(255,255,255,0.4)"
                                        style={{ marginTop: 16 }}
                                    />
                                ) : error ? (
                                    <EmptyState message={error} />
                                ) : jobs.length === 0 ? (
                                    <EmptyState message="No jobs yet" />
                                ) : (
                                    <>
                                        <Text style={styles.sectionLabel}>Recent Jobs</Text>
                                        {jobs.slice(0, 10).map((job) => (
                                            <JobRow key={job.job_id} job={job} />
                                        ))}
                                    </>
                                )}

                                <TouchableOpacity
                                    style={styles.viewAllButton}
                                    activeOpacity={0.8}
                                    onPress={() => {
                                        handleClose();
                                        setTimeout(() => router.push('/(tabs)/jobs' as any), 320);
                                    }}
                                >
                                    <Layers size={16} color={Colors.palette.inkBlack} />
                                    <Text style={styles.viewAllText}>View All Jobs</Text>
                                </TouchableOpacity>
                            </ScrollView>
                        </>
                    )}
                </Animated.View>
            </Modal>

            {/* Notification detail modal — rendered outside the slide panel */}
            <NotificationDetailModal
                notification={selectedNotification}
                onClose={handleDetailClose}
            />
        </>
    );
}

// ─────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    backdrop: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(7, 7, 18, 0.72)',
    },
    panel: {
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        height: PANEL_HEIGHT,
        backgroundColor: Colors.palette.shadowGrey,
        borderTopLeftRadius: 28,
        borderTopRightRadius: 28,
        overflow: 'hidden',
    },
    dragArea: {
        alignItems: 'center',
        paddingTop: 12,
        paddingBottom: 4,
    },
    handle: {
        width: 36,
        height: 4,
        borderRadius: 2,
        backgroundColor: 'rgba(255, 255, 255, 0.15)',
    },
    panelHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 24,
        paddingTop: 8,
        paddingBottom: 16,
    },
    panelTitleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    panelTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: Colors.palette.white,
        letterSpacing: 0.2,
    },
    unreadBadge: {
        backgroundColor: Colors.palette.white,
        borderRadius: 10,
        minWidth: 20,
        height: 20,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 5,
        marginLeft: 4,
    },
    unreadBadgeText: {
        color: Colors.palette.inkBlack,
        fontSize: 11,
        fontWeight: '700',
    },
    closeButton: {
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(255, 255, 255, 0.07)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    tabRow: {
        flexDirection: 'row',
        marginHorizontal: 24,
        backgroundColor: 'rgba(255, 255, 255, 0.06)',
        borderRadius: 40,
        padding: 4,
        marginBottom: 20,
        gap: 4,
    },
    tabPill: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        paddingVertical: 10,
        borderRadius: 36,
    },
    tabPillActive: {
        backgroundColor: Colors.palette.white,
    },
    tabPillText: {
        fontSize: 13,
        fontWeight: '600',
        color: 'rgba(255,255,255,0.5)',
    },
    tabPillTextActive: {
        color: Colors.palette.inkBlack,
    },
    scrollArea: {
        flex: 1,
    },
    scrollContent: {
        paddingHorizontal: 24,
        paddingBottom: 40,
    },
    sectionLabel: {
        fontSize: 11,
        fontWeight: '700',
        color: 'rgba(255,255,255,0.35)',
        letterSpacing: 1.1,
        textTransform: 'uppercase',
        marginBottom: 10,
    },
    endNote: {
        textAlign: 'center',
        fontSize: 13,
        color: 'rgba(255,255,255,0.25)',
        marginTop: 28,
        marginBottom: 8,
    },
    jobStatsRow: {
        flexDirection: 'row',
        marginHorizontal: 24,
        backgroundColor: 'rgba(255,255,255,0.04)',
        borderRadius: 16,
        paddingVertical: 14,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.07)',
    },
    jobStat: {
        flex: 1,
        alignItems: 'center',
    },
    jobStatValue: {
        fontSize: 22,
        fontWeight: '700',
    },
    jobStatLabel: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.4)',
        marginTop: 2,
        fontWeight: '500',
    },
    jobStatDivider: {
        width: 1,
        backgroundColor: 'rgba(255,255,255,0.08)',
        marginVertical: 4,
    },
    viewAllButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: Colors.palette.white,
        borderRadius: 16,
        paddingVertical: 14,
        marginTop: 20,
    },
    viewAllText: {
        fontSize: 15,
        fontWeight: '700',
        color: Colors.palette.inkBlack,
    },
});

// ─────────────────────────────────────────────────────────────
// Notification card styles
// ─────────────────────────────────────────────────────────────

const notifStyles = StyleSheet.create({
    card: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        backgroundColor: 'rgba(255,255,255,0.05)',
        borderRadius: 16,
        padding: 14,
        marginBottom: 10,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.08)',
        gap: 12,
    },
    cardRead: {
        opacity: 0.55,
    },
    iconWrap: {
        width: 36,
        height: 36,
        borderRadius: 10,
        backgroundColor: 'rgba(252, 254, 255, 0.08)',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
    },
    content: {
        flex: 1,
    },
    titleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginBottom: 3,
    },
    title: {
        fontSize: 14,
        fontWeight: '600',
        color: Colors.palette.white,
        flex: 1,
    },
    unreadDot: {
        width: 7,
        height: 7,
        borderRadius: 3.5,
        backgroundColor: Colors.palette.white,
        flexShrink: 0,
    },
    body: {
        fontSize: 13,
        color: 'rgba(255,255,255,0.55)',
        lineHeight: 18,
    },
    timestamp: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.3)',
        marginTop: 6,
    },
});

// ─────────────────────────────────────────────────────────────
// Job row styles
// ─────────────────────────────────────────────────────────────

const jobStyles = StyleSheet.create({
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(255,255,255,0.04)',
        borderRadius: 14,
        paddingVertical: 12,
        paddingHorizontal: 14,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.07)',
        gap: 12,
    },
    iconWrap: {
        width: 36,
        height: 36,
        borderRadius: 10,
        backgroundColor: 'rgba(255,255,255,0.06)',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
    },
    info: {
        flex: 1,
    },
    jobId: {
        fontSize: 14,
        fontWeight: '600',
        color: Colors.palette.white,
    },
    status: {
        fontSize: 12,
        fontWeight: '500',
        marginTop: 2,
    },
    meta: {
        alignItems: 'flex-end',
        gap: 4,
    },
    time: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.3)',
    },
});

// ─────────────────────────────────────────────────────────────
// Empty state styles
// ─────────────────────────────────────────────────────────────

const emptyStyles = StyleSheet.create({
    wrap: {
        flex: 1,
        alignItems: 'center',
        paddingTop: 48,
    },
    text: {
        fontSize: 14,
        color: 'rgba(255,255,255,0.3)',
        textAlign: 'center',
    },
});

// ─────────────────────────────────────────────────────────────
// Notification detail modal styles
// ─────────────────────────────────────────────────────────────

const detailStyles = StyleSheet.create({
    backdrop: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(7, 7, 18, 0.80)',
    },
    centeredWrap: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 24,
    },
    card: {
        width: '100%',
        backgroundColor: Colors.palette.shadowGrey,
        borderRadius: 24,
        padding: 24,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.09)',
    },
    headerRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 20,
    },
    iconWrap: {
        width: 44,
        height: 44,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
    },
    closeBtn: {
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(255,255,255,0.06)',
        alignItems: 'center',
        justifyContent: 'center',
    },
    title: {
        fontSize: 20,
        fontWeight: '700',
        color: Colors.palette.white,
        marginBottom: 10,
        letterSpacing: 0.1,
    },
    body: {
        fontSize: 14,
        color: 'rgba(255,255,255,0.6)',
        lineHeight: 21,
        marginBottom: 24,
    },
    metaBlock: {
        backgroundColor: 'rgba(255,255,255,0.04)',
        borderRadius: 16,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.07)',
        marginBottom: 20,
        overflow: 'hidden',
    },
    metaRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 12,
    },
    metaDivider: {
        height: 1,
        backgroundColor: 'rgba(255,255,255,0.06)',
        marginHorizontal: 16,
    },
    metaLabel: {
        fontSize: 13,
        color: 'rgba(255,255,255,0.4)',
        fontWeight: '500',
    },
    metaValue: {
        fontSize: 13,
        color: Colors.palette.white,
        fontWeight: '600',
        maxWidth: '60%',
        textAlign: 'right',
    },
    monoValue: {
        fontVariant: ['tabular-nums'],
        letterSpacing: 0.5,
    },
    dismissBtn: {
        backgroundColor: Colors.palette.white,
        borderRadius: 16,
        paddingVertical: 14,
        alignItems: 'center',
    },
    dismissText: {
        fontSize: 15,
        fontWeight: '700',
        color: Colors.palette.inkBlack,
    },
});
