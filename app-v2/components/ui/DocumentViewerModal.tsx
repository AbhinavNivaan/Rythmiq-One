/**
 * DocumentViewerModal
 *
 * Responsive slide-up bottom sheet. Panel height is content-driven —
 * no fixed pixel values. Image uses an aspect ratio, info section is
 * natural height, and buttons are pinned at the very bottom with safe-area
 * padding applied dynamically.
 *
 * Usage:
 *   <DocumentViewerModal jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
 */

import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
    Animated,
    Modal,
    PanResponder,
    TouchableWithoutFeedback,
    View,
    Text,
    Image,
    TouchableOpacity,
    ActivityIndicator,
    Alert,
    StyleSheet,
    Dimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { X, Download, Share2, Calendar, FileText, PenLine, ImageIcon } from 'lucide-react-native';
import { useQuery } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi, JobStatus } from '../../services/api';
import { downloadJobOutput, shareFile, outputFormatToMime } from '../../services/download';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        });
    } catch {
        return '—';
    }
}

function documentTitle(job: JobStatus): string {
    return job.document_subtype || job.document_category || job.document_type || 'Document';
}

const STATUS_COLOR: Record<string, string> = {
    completed:  Colors.palette.green,
    processing: '#89C7FE',
    pending:    Colors.palette.amber,
    failed:     Colors.palette.red,
};

const STATUS_LABEL: Record<string, string> = {
    completed:  'Done',
    processing: 'Processing',
    pending:    'Pending',
    failed:     'Failed',
};

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
    /** Pass the full JobStatus from the list — contains complete metadata (subtype, category, etc.) */
    job: JobStatus | null;
    onClose: () => void;
}

export default function DocumentViewerModal({ job: listJob, onClose }: Props) {
    const jobId = listJob?.job_id ?? null;
    const insets = useSafeAreaInsets();

    const slideAnim       = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
    const backdropOpacity = useRef(new Animated.Value(0)).current;

    const [imageLoading, setImageLoading] = useState(true);
    const [imageError, setImageError]     = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [downloadProgress, setDownloadProgress] = useState(0);

    useEffect(() => {
        if (jobId) {
            setImageLoading(true);
            setImageError(false);
        }
    }, [jobId]);

    // Fetch fresh job data for live status + signed URLs.
    // listJob (passed in) is used for metadata — it has complete subtype/category fields
    // that the individual /jobs/{id} endpoint may not return.
    const { data: freshJob, isLoading } = useQuery({
        queryKey: ['job', jobId],
        queryFn: () => documentsApi.getJobStatus(jobId!),
        enabled: !!jobId,
        refetchInterval: (query) => {
            const s = query.state.data?.status;
            return s === 'processing' || s === 'pending' ? 5000 : false;
        },
    });

    // Merge: prefer listJob for metadata, freshJob for live status + URLs
    const job: JobStatus | undefined = listJob ? {
        ...listJob,
        ...(freshJob ? {
            status: freshJob.status,
            preview_url: freshJob.preview_url ?? listJob.preview_url,
            output_url: freshJob.output_url ?? listJob.output_url,
            output_encrypted: freshJob.output_encrypted ?? listJob.output_encrypted,
            output_format: freshJob.output_format ?? listJob.output_format,
            download_url: freshJob.download_url ?? listJob.download_url,
        } : {}),
    } : freshJob;

    // ── Animation ─────────────────────────────────────────────────────────────

    const openPanel = useCallback(() => {
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
    }, []);

    const closePanel = useCallback((callback?: () => void) => {
        Animated.parallel([
            Animated.timing(slideAnim, {
                toValue: SCREEN_HEIGHT,
                duration: 280,
                useNativeDriver: true,
            }),
            Animated.timing(backdropOpacity, {
                toValue: 0,
                duration: 250,
                useNativeDriver: true,
            }),
        ]).start(() => callback?.());
    }, []);

    useEffect(() => {
        if (jobId) {
            slideAnim.setValue(SCREEN_HEIGHT);
            backdropOpacity.setValue(0);
            openPanel();
        }
    }, [jobId]);

    const handleClose = useCallback(() => closePanel(onClose), [closePanel, onClose]);

    // ── Drag to dismiss ───────────────────────────────────────────────────────

    const panResponder = useRef(
        PanResponder.create({
            onStartShouldSetPanResponder: () => true,
            onMoveShouldSetPanResponder: (_, gs) => gs.dy > 5,
            onPanResponderMove: (_, gs) => {
                if (gs.dy > 0) slideAnim.setValue(gs.dy);
            },
            onPanResponderRelease: (_, gs) => {
                if (gs.dy > SCREEN_HEIGHT * 0.15 || gs.vy > 0.5) {
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

    // ── Actions ───────────────────────────────────────────────────────────────

    const handleDownload = useCallback(async () => {
        if (!job || job.status !== 'completed') return;

        const isEncrypted = job.output_encrypted === true;
        const downloadTarget =
            (!isEncrypted && job.output_url) ? job.output_url
            : job.preview_url               ? job.preview_url
            : null;

        if (!downloadTarget) {
            Alert.alert('File Not Ready', 'The processed file is not yet available.');
            return;
        }

        setIsDownloading(true);
        setDownloadProgress(0);
        try {
            const usingPreview = !(!isEncrypted && job.output_url) && !!job.preview_url;
            const { mimeType, ext } = outputFormatToMime(job.output_format);
            const fileExt  = usingPreview ? 'jpg' : ext;
            const fileMime = usingPreview ? 'image/jpeg' : mimeType;

            const result = await downloadJobOutput(
                jobId!,
                downloadTarget,
                (p) => setDownloadProgress(p.progress),
                fileExt,
            );
            if (!result.success) throw new Error(result.error || 'Download failed');
            await shareFile(result.localPath, { mimeType: fileMime, dialogTitle: 'Save Document' });
        } catch {
            Alert.alert('Download Failed', 'Could not download the file. Please try again.');
        } finally {
            setIsDownloading(false);
            setDownloadProgress(0);
        }
    }, [job, jobId]);

    const handleExport = useCallback(() => {
        if (!jobId) return;
        handleClose();
        setTimeout(() => {
            router.push({ pathname: '/(tabs)/portal-selector', params: { documentId: jobId } } as any);
        }, 320);
    }, [jobId, handleClose]);

    // ── Render ────────────────────────────────────────────────────────────────

    if (!jobId) return null;

    const isCompleted = job?.status === 'completed';
    const statusColor = STATUS_COLOR[job?.status ?? 'pending'] ?? Colors.palette.amber;
    const statusLabel = STATUS_LABEL[job?.status ?? 'pending'] ?? (job?.status ?? '');

    // Title: explicit name → subtype → category → type
    const title = job?.document_name || job?.document_subtype || job?.document_category || job?.document_type || '—';

    // Type badge: subtype is most specific (e.g. "Personal Signature" not "signature")
    const typeLabel = job?.document_subtype || job?.document_category || job?.document_type || 'Document';

    const TypeIcon =
        job?.document_type === 'signature' ? PenLine :
        job?.document_type === 'photo'     ? ImageIcon :
        FileText;

    // Bottom padding respects the device safe area (notch / gesture bar)
    const bottomPad = Math.max(insets.bottom, 16);

    return (
        <Modal
            visible={!!jobId}
            transparent
            animationType="none"
            statusBarTranslucent
            onRequestClose={handleClose}
        >
            {/* Backdrop */}
            <TouchableWithoutFeedback onPress={handleClose}>
                <Animated.View style={[styles.backdrop, { opacity: backdropOpacity }]} />
            </TouchableWithoutFeedback>

            {/* Panel — height driven by content */}
            <Animated.View style={[styles.panel, { transform: [{ translateY: slideAnim }] }]}>

                {/* Drag handle row */}
                <View {...panResponder.panHandlers} style={styles.dragArea}>
                    <View style={styles.handle} />
                </View>

                {/* Close button */}
                <TouchableOpacity style={styles.closeBtn} onPress={handleClose} activeOpacity={0.7}>
                    <X size={16} color="rgba(255,255,255,0.5)" />
                </TouchableOpacity>

                {/* ── Document image — responsive aspect ratio ─────────────── */}
                <View style={styles.imageArea}>
                    {isLoading && (
                        <ActivityIndicator size="large" color="#555" />
                    )}

                    {!isLoading && isCompleted && job.preview_url && !imageError && (
                        <>
                            {imageLoading && (
                                <ActivityIndicator
                                    style={StyleSheet.absoluteFill}
                                    size="large"
                                    color="#555"
                                />
                            )}
                            <Image
                                source={{ uri: job.preview_url }}
                                style={styles.docImage}
                                resizeMode="contain"
                                onLoad={() => setImageLoading(false)}
                                onError={() => { setImageLoading(false); setImageError(true); }}
                            />
                        </>
                    )}

                    {!isLoading && (!isCompleted || !job?.preview_url || imageError) && (
                        <View style={styles.placeholderInner}>
                            {job?.status === 'processing' || job?.status === 'pending' ? (
                                <>
                                    <ActivityIndicator size="large" color="#89C7FE" />
                                    <Text style={styles.placeholderText}>
                                        {job.status === 'processing' ? 'Processing…' : 'Queued'}
                                    </Text>
                                </>
                            ) : (
                                <>
                                    <FileText size={40} color="#444" />
                                    <Text style={styles.placeholderText}>No preview available</Text>
                                </>
                            )}
                        </View>
                    )}
                </View>

                {/* ── Info + actions ───────────────────────────────────────── */}
                <View style={[styles.info, { paddingBottom: bottomPad }]}>
                    <Text style={styles.docTitle} numberOfLines={1}>{title}</Text>

                    <View style={styles.badgeRow}>
                        <View style={styles.typeBadge}>
                            <TypeIcon size={12} color="#888" />
                            <Text style={styles.typeBadgeText}>{typeLabel}</Text>
                        </View>
                        <View style={[styles.statusBadge, {
                            backgroundColor: statusColor + '22',
                            borderColor: statusColor + '55',
                        }]}>
                            <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
                            <Text style={[styles.statusBadgeText, { color: statusColor }]}>{statusLabel}</Text>
                        </View>
                    </View>

                    {job?.created_at && (
                        <View style={styles.metaRow}>
                            <Calendar size={14} color="#555" />
                            <Text style={styles.metaText}>{formatDate(job.created_at)}</Text>
                        </View>
                    )}

                    <View style={styles.actionRow}>
                        {/* Export — primary action */}
                        <TouchableOpacity
                            style={[styles.actionBtn, styles.exportBtn, !isCompleted && styles.btnDisabled]}
                            onPress={handleExport}
                            activeOpacity={0.85}
                            disabled={!isCompleted}
                        >
                            <Share2 size={17} color={Colors.palette.inkBlack} />
                            <Text style={styles.exportBtnText}>Export</Text>
                        </TouchableOpacity>

                        {/* Download — secondary action */}
                        <TouchableOpacity
                            style={[styles.actionBtn, styles.downloadBtn, (!isCompleted || isDownloading) && styles.btnDisabled]}
                            onPress={handleDownload}
                            activeOpacity={0.8}
                            disabled={!isCompleted || isDownloading}
                        >
                            {isDownloading ? (
                                <ActivityIndicator size="small" color={Colors.palette.white} />
                            ) : (
                                <>
                                    <Download size={17} color={Colors.palette.white} />
                                    <Text style={styles.downloadBtnText}>
                                        {downloadProgress > 0 ? `${Math.round(downloadProgress * 100)}%` : 'Download'}
                                    </Text>
                                </>
                            )}
                        </TouchableOpacity>
                    </View>
                </View>

            </Animated.View>
        </Modal>
    );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
    backdrop: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(0,0,0,0.72)',
    },

    // Panel wraps content — no fixed height
    panel: {
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: Colors.palette.inkBlack,
        borderTopLeftRadius: 24,
        borderTopRightRadius: 24,
        overflow: 'hidden',
    },

    // Drag handle
    dragArea: {
        alignItems: 'center',
        paddingTop: 10,
        paddingBottom: 4,
    },
    handle: {
        width: 36,
        height: 4,
        borderRadius: 2,
        backgroundColor: 'rgba(255,255,255,0.15)',
    },

    // Close button — overlays top-right of panel
    closeBtn: {
        position: 'absolute',
        top: 10,
        right: 16,
        width: 30,
        height: 30,
        borderRadius: 15,
        backgroundColor: 'rgba(255,255,255,0.08)',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10,
    },

    // Image: full width, 16:9 aspect ratio — responsive to any screen width
    imageArea: {
        width: '100%',
        aspectRatio: 16 / 9,
        backgroundColor: '#0D0D0D',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
    },
    docImage: {
        width: '100%',
        height: '100%',
    },
    placeholderInner: {
        alignItems: 'center',
        gap: 12,
    },
    placeholderText: {
        fontSize: 13,
        color: '#555',
    },

    // Info section — natural height, no flex stretching
    info: {
        paddingHorizontal: 24,
        paddingTop: 18,
        gap: 12,
    },
    docTitle: {
        fontSize: 22,
        fontWeight: '700',
        color: Colors.palette.white,
    },

    // Badges
    badgeRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    typeBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 5,
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.12)',
    },
    typeBadgeText: {
        fontSize: 12,
        color: '#888',
        fontWeight: '500',
    },
    statusBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 20,
        borderWidth: 1,
    },
    statusDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
    },
    statusBadgeText: {
        fontSize: 12,
        fontWeight: '600',
    },

    // Date row
    metaRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    metaText: {
        fontSize: 14,
        color: '#555',
    },

    // Action buttons
    actionRow: {
        flexDirection: 'row',
        gap: 12,
        marginTop: 4,
    },
    actionBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        height: 54,
        borderRadius: 27,
    },
    btnDisabled: {
        opacity: 0.35,
    },
    // Export = primary (green filled)
    exportBtn: {
        backgroundColor: Colors.palette.green,
    },
    exportBtnText: {
        fontSize: 15,
        fontWeight: '600',
        color: Colors.palette.inkBlack,
    },
    // Download = secondary (dark outlined)
    downloadBtn: {
        backgroundColor: '#1C1C1E',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.12)',
    },
    downloadBtnText: {
        fontSize: 15,
        fontWeight: '600',
        color: Colors.palette.white,
    },
});
