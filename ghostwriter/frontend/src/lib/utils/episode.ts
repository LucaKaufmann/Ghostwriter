import type { DigestStatusBadgeVariant } from '$lib/utils/digest';

const ACTIVE_EPISODE_STATUSES = new Set(['pending', 'generating_script', 'generating_audio']);

export function getEpisodeStatusBadgeVariant(status: string): DigestStatusBadgeVariant {
	switch (status) {
		case 'ready':
			return 'default';
		case 'pending':
		case 'generating_script':
		case 'generating_audio':
			return 'secondary';
		case 'failed':
			return 'destructive';
		default:
			return 'outline';
	}
}

export function getEpisodeStatusLabel(status: string): string {
	switch (status) {
		case 'pending':
			return 'Queued';
		case 'generating_script':
			return 'Generating script';
		case 'generating_audio':
			return 'Generating audio';
		case 'ready':
			return 'Ready';
		case 'failed':
			return 'Failed';
		default:
			return status;
	}
}

export function isEpisodeActive(status: string): boolean {
	return ACTIVE_EPISODE_STATUSES.has(status);
}

export function formatDuration(seconds: number): string {
	const minutes = Math.floor(seconds / 60);
	const secs = seconds % 60;
	if (minutes === 0) return `${secs}s`;
	return `${minutes}m ${secs}s`;
}

export function formatPlayerTime(totalSeconds: number): string {
	const h = Math.floor(totalSeconds / 3600);
	const m = Math.floor((totalSeconds % 3600) / 60);
	const s = Math.floor(totalSeconds % 60);
	const ss = s.toString().padStart(2, '0');
	return h > 0 ? `${h}:${m.toString().padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function formatCost(cents: number): string {
	return `$${(cents / 100).toFixed(2)}`;
}
