import { api } from '$lib/api';

export type DigestStatusBadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';
export type DigestFileFormat = 'epub' | 'pdf';

export function getDigestStatusBadgeVariant(status: string): DigestStatusBadgeVariant {
	switch (status) {
		case 'completed':
			return 'default';
		case 'processing':
			return 'secondary';
		case 'failed':
			return 'destructive';
		default:
			return 'outline';
	}
}

export async function downloadDigestFile(filename: string): Promise<void> {
	const { blob, filename: resolved } = await api.downloadDigest(filename);
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = resolved;
	anchor.click();
	URL.revokeObjectURL(url);
}

export async function downloadDigestFileById(
	digestId: string,
	format: DigestFileFormat,
	fallbackFilename: string
): Promise<void> {
	const { blob, filename: resolved } = await api.downloadDigestById(digestId, format, fallbackFilename);
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = resolved;
	anchor.click();
	URL.revokeObjectURL(url);
}
