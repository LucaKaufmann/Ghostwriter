<script lang="ts">
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api, type Schedule, type ScheduleUpdate, type DigestPeriod, type APITokenResponse, type LogFileInfo, type WallabagConfigResponse, type WallabagConfigUpdate, type PreviewResponse, type ClientConfigUpdate, type KoreaderPluginDownloadRequest } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import * as Select from '$lib/components/ui/select';
	import * as Tabs from '$lib/components/ui/tabs';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Switch } from '$lib/components/ui/switch';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { formatUTCDate, parseUTC } from '$lib/utils/date';
	import { toast } from 'svelte-sonner';
	import { currentUser } from '$lib/stores/auth';
	import {
		Settings,
		Clock,
		Brain,
		Save,
		Loader2,
		CheckCircle2,
		Copy,
		Eye,
		EyeOff,
		Key,
		Plus,
		Trash2,
		AlertTriangle,
		FileText,
		Download,
		ChevronDown,
		ChevronUp,
		Plug,
		TestTube2,
		Search
	} from 'lucide-svelte';

	const queryClient = useQueryClient();

	// Queries
	const configQuery = createQuery(() => ({
		queryKey: ['config'],
		queryFn: () => api.getPublicConfig()
	}));

	const clientConfigQuery = createQuery(() => ({
		queryKey: ['client-config'],
		queryFn: () => api.getClientConfig()
	}));

	const schedulesQuery = createQuery(() => ({
		queryKey: ['schedules'],
		queryFn: () => api.getSchedules()
	}));

	const manualCoversQuery = createQuery(() => ({
		queryKey: ['manual-covers'],
		queryFn: () => api.listManualCovers()
	}));

	const tokensQuery = createQuery(() => ({
		queryKey: ['api-tokens'],
		queryFn: () => api.getAPITokens()
	}));

	const logFilesQuery = createQuery(() => ({
		queryKey: ['log-files'],
		queryFn: () => api.getLogFiles()
	}));

	// Mutations
	const updateScheduleMutation = createMutation(() => ({
		mutationFn: ({ period, data }: { period: DigestPeriod; data: ScheduleUpdate }) =>
			api.updateSchedule(period, data),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['schedules'] });
			toast.success('Schedule updated');
		},
		onError: (err: Error) => {
			toast.error('Failed to update schedule', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const createTokenMutation = createMutation(() => ({
		mutationFn: (name: string) => api.createAPIToken({ name }),
		onSuccess: (data) => {
			queryClient.invalidateQueries({ queryKey: ['api-tokens'] });
			newlyCreatedToken = data.token;
			showNewTokenDialog = true;
			newTokenName = '';
			showCreateTokenDialog = false;
		},
		onError: (err: Error) => {
			toast.error('Failed to create token', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const revokeTokenMutation = createMutation(() => ({
		mutationFn: (tokenId: string) => api.revokeAPIToken(tokenId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['api-tokens'] });
			toast.success('Token revoked');
			tokenToRevoke = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to revoke token', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const downloadKoreaderPluginMutation = createMutation(() => ({
		mutationFn: (data: KoreaderPluginDownloadRequest) => api.downloadKoreaderPlugin(data),
		onSuccess: ({ blob, filename }) => {
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = filename;
			anchor.click();
			URL.revokeObjectURL(url);

			queryClient.invalidateQueries({ queryKey: ['api-tokens'] });
			toast.success('KOReader plugin downloaded', {
				description: 'A new API token was created and embedded in the plugin.'
			});
			showKoreaderPluginDialog = false;
		},
		onError: (err: Error) => {
			toast.error('Failed to download KOReader plugin', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const wallabagConfigQuery = createQuery(() => ({
		queryKey: ['wallabag-config'],
		queryFn: () => api.getWallabagConfig()
	}));

	const whisperModelsQuery = createQuery(() => ({
		queryKey: ['whisper-models'],
		queryFn: () => api.getWhisperModels(),
		refetchInterval: (query) => {
			const data = query.state.data;
			if (!data) return false;
			return data.models.some((model) => model.status === 'downloading') ? 2000 : false;
		}
	}));

	const updateWallabagMutation = createMutation(() => ({
		mutationFn: (data: WallabagConfigUpdate) => api.updateWallabagConfig(data),
		onSuccess: (data) => {
			wbForm = {
				url: data.url,
				client_id: data.client_id,
				client_secret: data.client_secret,
				username: data.username,
				password: data.password,
				mode: data.mode,
				max_articles: data.max_articles,
				tag_on_process: data.tag_on_process
			};
			queryClient.invalidateQueries({ queryKey: ['wallabag-config'] });
			queryClient.invalidateQueries({ queryKey: ['client-config'] });
			toast.success('Wallabag configuration saved');
		},
		onError: (err: Error) => {
			toast.error('Failed to save Wallabag config', { description: err.message });
		}
	}));

	const testWallabagMutation = createMutation(() => ({
		mutationFn: () => api.testWallabagConnection(),
		onSuccess: (data) => {
			if (data.status === 'ok') {
				toast.success('Wallabag connection successful');
			} else {
				toast.error('Wallabag connection failed', { description: data.detail });
			}
		},
		onError: (err: Error) => {
			toast.error('Wallabag test failed', { description: err.message });
		}
	}));

	const updateClientConfigMutation = createMutation(() => ({
		mutationFn: (data: ClientConfigUpdate) => api.updateClientConfig(data),
		onSuccess: (data, variables) => {
			const coverFields: (keyof ClientConfigUpdate)[] = [
				'cover_enabled',
				'cover_provider',
				'cover_quality',
				'cover_prompt',
				'cover_openai_api_key',
				'cover_gemini_api_key'
			];
			if (coverFields.some((field) => field in variables)) {
				coverEnabled = data.cover_enabled ?? false;
				coverProvider = (data.cover_provider as 'gpt-image-1' | 'nano-banana') ?? 'gpt-image-1';
				coverQuality = (data.cover_quality as 'low' | 'medium' | 'high') ?? 'low';
				coverPrompt = data.cover_prompt ?? '';
				coverOpenAIKey = data.cover_openai_api_key ?? '';
				coverGeminiKey = data.cover_gemini_api_key ?? '';
			}
			queryClient.invalidateQueries({ queryKey: ['client-config'] });
		},
		onError: (err: Error) => {
			toast.error('Failed to update config', { description: err.message });
		}
	}));

	const downloadWhisperModelMutation = createMutation(() => ({
		mutationFn: (model: string) => api.downloadWhisperModel({ model }),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['whisper-models'] });
			toast.success('Model download started');
		},
		onError: (err: Error) => {
			toast.error('Failed to download model', { description: err.message });
		}
	}));

	const deleteWhisperModelMutation = createMutation(() => ({
		mutationFn: (model: string) => api.deleteWhisperModel(model),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['whisper-models'] });
			toast.success('Model removed');
		},
		onError: (err: Error) => {
			toast.error('Failed to remove model', { description: err.message });
		}
	}));

	const setActiveWhisperModelMutation = createMutation(() => ({
		mutationFn: (model: string) => api.setActiveWhisperModel({ model }),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['whisper-models'] });
			toast.success('Active model updated');
		},
		onError: (err: Error) => {
			toast.error('Failed to update active model', { description: err.message });
		}
	}));

	const uploadManualCoverMutation = createMutation(() => ({
		mutationFn: (file: File) => api.uploadManualCover(file),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['manual-covers'] });
			toast.success('Manual cover uploaded');
		},
		onError: (err: Error) => {
			toast.error('Failed to upload cover', { description: err.message });
		}
	}));

	const activateManualCoverMutation = createMutation(() => ({
		mutationFn: (coverId: string) => api.activateManualCover(coverId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['manual-covers'] });
			toast.success('Active cover updated');
		},
		onError: (err: Error) => {
			toast.error('Failed to activate cover', { description: err.message });
		}
	}));

	const deleteManualCoverMutation = createMutation(() => ({
		mutationFn: (coverId: string) => api.deleteManualCover(coverId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['manual-covers'] });
			toast.success('Cover deleted');
		},
		onError: (err: Error) => {
			toast.error('Failed to delete cover', { description: err.message });
		}
	}));

	// Preview state
	let wallabagPreview = $state<PreviewResponse | null>(null);
	let newsletterPreview = $state<PreviewResponse | null>(null);
	let settingsSection = $state<'general' | 'schedule' | 'integrations' | 'security' | 'logs'>(
		'general'
	);

	const previewWallabagMutation = createMutation(() => ({
		mutationFn: () => api.previewWallabag(),
		onSuccess: (data) => {
			wallabagPreview = data;
			if (data.status === 'error') {
				toast.error('Wallabag preview failed', { description: data.detail });
			}
		},
		onError: (err: Error) => {
			toast.error('Wallabag preview failed', { description: err.message });
		}
	}));

	const previewNewsletterMutation = createMutation(() => ({
		mutationFn: () => api.previewNewsletters(),
		onSuccess: (data) => {
			newsletterPreview = data;
			if (data.status === 'error') {
				toast.error('Newsletter preview failed', { description: data.detail });
			}
		},
		onError: (err: Error) => {
			toast.error('Newsletter preview failed', { description: err.message });
		}
	}));

	const clearWallabagSeenMutation = createMutation(() => ({
		mutationFn: () => api.clearWallabagSeen(),
		onSuccess: (data) => {
			toast.success(`Cleared ${data.cleared} Wallabag seen article${data.cleared === 1 ? '' : 's'}`);
		},
		onError: (err: Error) => {
			toast.error('Failed to clear Wallabag history', { description: err.message });
		}
	}));

	const clearNewsletterSeenMutation = createMutation(() => ({
		mutationFn: () => api.clearNewsletterSeen(),
		onSuccess: (data) => {
			toast.success(`Cleared ${data.cleared} newsletter seen article${data.cleared === 1 ? '' : 's'}`);
		},
		onError: (err: Error) => {
			toast.error('Failed to clear newsletter history', { description: err.message });
		}
	}));

	// Wallabag form state
	let wallabagExpanded = $state(false);
	let wbForm = $state<WallabagConfigUpdate>({});
	let wbFormInitialized = $state(false);

	let wbEnabled = $state(true);

	// Transcription config state
	let whisperProvider = $state<'local' | 'openai' | 'auto'>('local');
	let whisperTimeout = $state(30);
	let whisperProviderInitialized = $state(false);
	let coverEnabled = $state(false);
	let coverProvider = $state<'gpt-image-1' | 'nano-banana'>('gpt-image-1');
	let coverQuality = $state<'low' | 'medium' | 'high'>('low');
	let coverPrompt = $state('');
	let coverOpenAIKey = $state('');
	let coverGeminiKey = $state('');
	let coverSettingsInitialized = $state(false);
	let manualCoverInput: HTMLInputElement | null = $state(null);

	$effect(() => {
		const data = wallabagConfigQuery.data;
		if (data && !wbFormInitialized) {
			wbForm = {
				url: data.url,
				client_id: data.client_id,
				client_secret: data.client_secret,
				username: data.username,
				password: data.password,
				mode: data.mode,
				max_articles: data.max_articles,
				tag_on_process: data.tag_on_process
			};
			wbEnabled = data.enabled;
			wbFormInitialized = true;
		}
	});

	$effect(() => {
		const data = clientConfigQuery.data;
		if (data && !whisperProviderInitialized) {
			whisperProvider = (data.whisper_provider as 'local' | 'openai' | 'auto') ?? 'local';
			whisperTimeout = data.whisper_timeout_minutes ?? 30;
			whisperProviderInitialized = true;
		}
	});

	$effect(() => {
		const data = clientConfigQuery.data;
		if (data && !coverSettingsInitialized) {
			coverEnabled = data.cover_enabled ?? false;
			coverProvider = (data.cover_provider as 'gpt-image-1' | 'nano-banana') ?? 'gpt-image-1';
			coverQuality = (data.cover_quality as 'low' | 'medium' | 'high') ?? 'low';
			coverPrompt = data.cover_prompt ?? '';
			coverOpenAIKey = data.cover_openai_api_key ?? '';
			coverGeminiKey = data.cover_gemini_api_key ?? '';
			coverSettingsInitialized = true;
		}
	});

	function saveWhisperProvider() {
		updateClientConfigMutation.mutate({ whisper_provider: whisperProvider });
	}

	function saveWhisperTimeout() {
		const clamped = Math.max(1, Math.min(120, whisperTimeout));
		whisperTimeout = clamped;
		updateClientConfigMutation.mutate({ whisper_timeout_minutes: clamped });
	}

	function saveCoverSettings() {
		updateClientConfigMutation.mutate({
			cover_enabled: coverEnabled,
			cover_provider: coverProvider,
			cover_quality: coverQuality,
			cover_prompt: coverPrompt.trim(),
			cover_openai_api_key: coverOpenAIKey.trim(),
			cover_gemini_api_key: coverGeminiKey.trim()
		});
	}

	function hasCoverSettingsChanged(): boolean {
		const data = clientConfigQuery.data;
		if (!data) return false;
		return (
			coverEnabled !== (data.cover_enabled ?? false) ||
			coverProvider !== (data.cover_provider ?? 'gpt-image-1') ||
			coverQuality !== (data.cover_quality ?? 'low') ||
			coverPrompt.trim() !== (data.cover_prompt ?? '') ||
			coverOpenAIKey.trim() !== (data.cover_openai_api_key ?? '') ||
			coverGeminiKey.trim() !== (data.cover_gemini_api_key ?? '')
		);
	}

	function saveWallabag() {
		updateWallabagMutation.mutate(wbForm);
	}

	function triggerManualCoverUpload() {
		manualCoverInput?.click();
	}

	function handleManualCoverFileChange(event: Event) {
		const target = event.currentTarget as HTMLInputElement;
		const file = target.files?.[0];
		if (!file) return;
		uploadManualCoverMutation.mutate(file);
		target.value = '';
	}

	function formatBytes(value: number): string {
		if (value < 1024) return `${value} B`;
		if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
		return `${(value / (1024 * 1024)).toFixed(1)} MB`;
	}

	function hasWallabagChanged(): boolean {
		const data = wallabagConfigQuery.data;
		if (!data) return false;
		return (
			wbForm.url !== data.url ||
			wbForm.client_id !== data.client_id ||
			wbForm.client_secret !== data.client_secret ||
			wbForm.username !== data.username ||
			wbForm.password !== data.password ||
			wbForm.mode !== data.mode ||
			wbForm.max_articles !== data.max_articles ||
			wbForm.tag_on_process !== data.tag_on_process
		);
	}

	// State
	let showToken = $state(false);
	let copiedToken = $state(false);

	// Token management state
	let showCreateTokenDialog = $state(false);
	let newTokenName = $state('');
	let showNewTokenDialog = $state(false);
	let newlyCreatedToken = $state('');
	let copiedNewToken = $state(false);
	let tokenToRevoke = $state<APITokenResponse | null>(null);
	let showKoreaderPluginDialog = $state(false);
	let koreaderPluginTokenName = $state('KOReader Plugin');
	let koreaderPluginServerUrl = $state('');

	// Get stored token (JWT)
	const storedToken = $derived(api.getToken() || '');

	// Schedule form state (initialized from query data)
	let scheduleEdits = $state<Record<string, { hour: number; minute: number; enabled: boolean }>>({});

	// Initialize schedule edits when data loads
	$effect(() => {
		const schedules = schedulesQuery.data;
		if (schedules && Object.keys(scheduleEdits).length === 0) {
			schedules.forEach((s) => {
				scheduleEdits[s.period] = {
					hour: s.hour,
					minute: s.minute,
					enabled: s.enabled
				};
			});
		}
	});

	function formatTime(hour: number, minute: number): string {
		return `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
	}

	function parseTime(timeStr: string): { hour: number; minute: number } | null {
		const match = timeStr.match(/^(\d{1,2}):(\d{2})$/);
		if (!match) return null;
		const hour = parseInt(match[1], 10);
		const minute = parseInt(match[2], 10);
		if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
		return { hour, minute };
	}

	function handleTimeChange(period: string, timeStr: string) {
		const parsed = parseTime(timeStr);
		if (parsed && scheduleEdits[period]) {
			scheduleEdits[period].hour = parsed.hour;
			scheduleEdits[period].minute = parsed.minute;
		}
	}

	function handleEnabledChange(period: string, enabled: boolean) {
		if (scheduleEdits[period]) {
			scheduleEdits[period].enabled = enabled;
		}
	}

	function saveSchedule(period: DigestPeriod) {
		const edit = scheduleEdits[period];
		if (!edit) return;
		updateScheduleMutation.mutate({
			period,
			data: {
				hour: edit.hour,
				minute: edit.minute,
				enabled: edit.enabled
			}
		});
	}

	function hasScheduleChanged(period: string): boolean {
		const original = schedulesQuery.data?.find((s) => s.period === period);
		const edit = scheduleEdits[period];
		if (!original || !edit) return false;
		return (
			original.hour !== edit.hour ||
			original.minute !== edit.minute ||
			original.enabled !== edit.enabled
		);
	}

	function copyToClipboard(text: string): boolean {
		// Fallback for non-secure contexts (HTTP)
		const textarea = document.createElement('textarea');
		textarea.value = text;
		textarea.style.position = 'fixed';
		textarea.style.opacity = '0';
		document.body.appendChild(textarea);
		textarea.select();
		try {
			document.execCommand('copy');
			return true;
		} catch {
			return false;
		} finally {
			document.body.removeChild(textarea);
		}
	}

	async function copyToken() {
		try {
			if (navigator.clipboard && window.isSecureContext) {
				await navigator.clipboard.writeText(storedToken);
			} else if (!copyToClipboard(storedToken)) {
				throw new Error('Copy failed');
			}
			copiedToken = true;
			toast.success('Token copied to clipboard');
			setTimeout(() => (copiedToken = false), 2000);
		} catch {
			toast.error('Failed to copy token');
		}
	}

	async function copyNewToken() {
		try {
			if (navigator.clipboard && window.isSecureContext) {
				await navigator.clipboard.writeText(newlyCreatedToken);
			} else if (!copyToClipboard(newlyCreatedToken)) {
				throw new Error('Copy failed');
			}
			copiedNewToken = true;
			toast.success('Token copied to clipboard');
			setTimeout(() => (copiedNewToken = false), 2000);
		} catch {
			toast.error('Failed to copy token');
		}
	}

	function openKoreaderPluginDialog() {
		if (!koreaderPluginServerUrl && typeof window !== 'undefined') {
			koreaderPluginServerUrl = window.location.origin;
		}
		showKoreaderPluginDialog = true;
	}

	function downloadKoreaderPlugin() {
		const tokenName = koreaderPluginTokenName.trim();
		if (!tokenName) {
			toast.error('Token name is required');
			return;
		}
		downloadKoreaderPluginMutation.mutate({
			token_name: tokenName,
			server_url: koreaderPluginServerUrl.trim() || undefined
		});
	}

	function formatNextRun(schedule: Schedule): string {
		if (!schedule.next_run_at) return 'Not scheduled';
		return parseUTC(schedule.next_run_at).toLocaleString('en-US', {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function formatFileSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function getDownloadProgress(model: { bytes_downloaded?: number | null; total_bytes?: number | null }): string | null {
		if (!model.total_bytes || model.total_bytes === 0 || model.bytes_downloaded == null) {
			return null;
		}
		const percent = Math.min(100, Math.round((model.bytes_downloaded / model.total_bytes) * 100));
		return `${percent}%`;
	}

	function formatDate(dateStr: string): string {
		return formatUTCDate(dateStr, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function formatLastUsed(dateStr: string | null): string {
		if (!dateStr) return 'Never used';
		const date = parseUTC(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffMins < 1) return 'Just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;
		return formatDate(dateStr);
	}

	async function downloadLog(filename: string) {
		try {
			const { blob, filename: resolved } = await api.downloadLog(filename);
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = resolved;
			anchor.click();
			URL.revokeObjectURL(url);
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast.error('Failed to download log', { description: message });
		}
	}
</script>

<svelte:head>
	<title>Settings - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Settings</h1>
		<p class="text-muted-foreground">Configure your Ghostwriter instance</p>
	</div>

	<Tabs.Root bind:value={settingsSection}>
		<Tabs.List class="grid h-auto w-full grid-cols-2 gap-2 bg-transparent p-0 md:grid-cols-5">
			<Tabs.Trigger value="general">General</Tabs.Trigger>
			<Tabs.Trigger value="schedule">Schedule</Tabs.Trigger>
			<Tabs.Trigger value="integrations">Integrations</Tabs.Trigger>
			<Tabs.Trigger value="security">Security</Tabs.Trigger>
			<Tabs.Trigger value="logs">Logs</Tabs.Trigger>
		</Tabs.List>

		<Tabs.Content value="general" class="mt-4 space-y-6">

			<!-- AI Configuration (Read-only) -->
			<Card.Root>
				<Card.Header>
					<Card.Title class="flex items-center gap-2">
						<Brain class="h-5 w-5" />
						AI Configuration
					</Card.Title>
					<Card.Description>
						AI settings are configured via environment variables on the server
					</Card.Description>
				</Card.Header>
				<Card.Content>
					{#if configQuery.isPending}
						<div class="space-y-3">
							<Skeleton class="h-4 w-48" />
							<Skeleton class="h-4 w-64" />
						</div>
					{:else if configQuery.data}
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="space-y-1">
								<Label class="text-muted-foreground">Provider</Label>
								<p class="font-medium">{configQuery.data.ai_provider}</p>
							</div>
							<div class="space-y-1">
								<Label class="text-muted-foreground">Model</Label>
								<p class="font-medium">{configQuery.data.ai_model}</p>
							</div>
						</div>
					{/if}
				</Card.Content>
			</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title class="flex items-center gap-2">
					<FileText class="h-5 w-5" />
					Digest Covers
				</Card.Title>
				<Card.Description>
					Generate an AI cover for each Ghostwriter digest
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-4">
				{#if clientConfigQuery.isPending}
					<div class="space-y-3">
						<Skeleton class="h-10 w-full" />
						<Skeleton class="h-10 w-full" />
						<Skeleton class="h-10 w-full" />
					</div>
				{:else if clientConfigQuery.data}
					<div class="flex items-center justify-between rounded-lg border p-3">
						<div>
							<p class="font-medium">AI cover generation</p>
							<p class="text-sm text-muted-foreground">Create a fresh image for every digest</p>
						</div>
						<Switch checked={coverEnabled} onCheckedChange={(checked) => (coverEnabled = checked)} />
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="cover-provider">Provider</Label>
							<select
								id="cover-provider"
								class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
								bind:value={coverProvider}
							>
								<option value="gpt-image-1">OpenAI (gpt-image-1)</option>
								<option value="nano-banana">Gemini (Nano Banana)</option>
							</select>
						</div>

						<div class="space-y-2">
							<Label for="cover-quality">Quality</Label>
							<select
								id="cover-quality"
								class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
								bind:value={coverQuality}
								disabled={coverProvider !== 'gpt-image-1'}
							>
								<option value="low">Low</option>
								<option value="medium">Medium</option>
								<option value="high">High</option>
							</select>
							<p class="text-xs text-muted-foreground">
								Quality tiers apply to gpt-image-1 only.
							</p>
						</div>
					</div>

					<div class="space-y-2">
						<Label for="cover-prompt">Prompt Add-on (optional)</Label>
						<Input
							id="cover-prompt"
							placeholder="e.g., geometric, high contrast, printmaking style"
							bind:value={coverPrompt}
						/>
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="cover-openai-key">OpenAI Cover API Key</Label>
							<Input
								id="cover-openai-key"
								type="password"
								placeholder="sk-..."
								bind:value={coverOpenAIKey}
							/>
							<p class="text-xs text-muted-foreground">
								Optional override for cover images only.
							</p>
						</div>
						<div class="space-y-2">
							<Label for="cover-gemini-key">Gemini Cover API Key</Label>
							<Input
								id="cover-gemini-key"
								type="password"
								placeholder="AIza..."
								bind:value={coverGeminiKey}
							/>
							<p class="text-xs text-muted-foreground">
								Optional override for cover images only.
							</p>
						</div>
					</div>

					<p class="text-xs text-muted-foreground">
						Saved keys are masked on reload. Clear a field and save to remove it.
					</p>

					<div class={`space-y-3 rounded-lg border p-3 ${coverEnabled ? 'opacity-60' : ''}`}>
						<div class="flex items-center justify-between gap-2">
							<div>
								<p class="font-medium">Manual Cover Library</p>
								<p class="text-xs text-muted-foreground">
									Upload covers, preview them, and choose the active manual cover.
								</p>
							</div>
							<Button
								size="sm"
								variant="outline"
								onclick={triggerManualCoverUpload}
								disabled={uploadManualCoverMutation.isPending}
							>
								{#if uploadManualCoverMutation.isPending}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{/if}
								Upload Cover
							</Button>
							<input
								class="hidden"
								type="file"
								accept="image/*"
								bind:this={manualCoverInput}
								onchange={handleManualCoverFileChange}
							/>
						</div>

						{#if coverEnabled}
							<p class="text-xs text-amber-700">
								AI cover generation is enabled. Manual covers are currently inactive.
							</p>
						{/if}

						{#if manualCoversQuery.isPending}
							<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
								{#each Array(4) as _}
									<div class="space-y-2 rounded-md border p-2">
										<Skeleton class="aspect-[5/8] w-full rounded-md" />
										<Skeleton class="h-4 w-3/4" />
									</div>
								{/each}
							</div>
						{:else if (manualCoversQuery.data?.covers?.length ?? 0) === 0}
							<p class="text-sm text-muted-foreground">
								No manual covers uploaded yet.
							</p>
						{:else}
							<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
								{#each manualCoversQuery.data?.covers ?? [] as cover}
									<div class="rounded-md border p-2">
										<div class="relative aspect-[5/8] overflow-hidden rounded-md border bg-muted">
											{#if cover.preview_data_url}
												<img src={cover.preview_data_url} alt={cover.name} class="h-full w-full object-cover" />
											{:else}
												<div class="flex h-full items-center justify-center text-xs text-muted-foreground">
													Preview unavailable
												</div>
											{/if}
											{#if cover.is_active}
												<span class="absolute right-2 top-2 rounded bg-primary px-2 py-1 text-xs text-primary-foreground">
													Active
												</span>
											{/if}
										</div>
										<p class="mt-2 truncate text-xs font-medium" title={cover.name}>{cover.name}</p>
										<p class="text-xs text-muted-foreground">{formatBytes(cover.size_bytes)}</p>
										<div class="mt-2 flex gap-2">
											<Button
												size="sm"
												variant="outline"
												class="flex-1"
												onclick={() => activateManualCoverMutation.mutate(cover.id)}
												disabled={cover.is_active || activateManualCoverMutation.isPending}
											>
												Set Active
											</Button>
											<Button
												size="sm"
												variant="outline"
												onclick={() => deleteManualCoverMutation.mutate(cover.id)}
												disabled={deleteManualCoverMutation.isPending}
											>
												<Trash2 class="h-4 w-4" />
											</Button>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>

					<div class="flex items-center justify-between gap-3">
						<p class="text-sm text-muted-foreground">Applies to future digests only.</p>
						<Button
							size="sm"
							onclick={saveCoverSettings}
							disabled={!hasCoverSettingsChanged() || updateClientConfigMutation.isPending}
						>
							{#if updateClientConfigMutation.isPending}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{:else}
								<Save class="mr-2 h-4 w-4" />
							{/if}
							Save
						</Button>
					</div>
				{/if}
			</Card.Content>
		</Card.Root>

			</Tabs.Content>
			<Tabs.Content value="schedule" class="mt-4 space-y-6">

	<!-- Schedule Configuration -->
	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<Clock class="h-5 w-5" />
				Digest Schedule
			</Card.Title>
			<Card.Description>
				Configure when automatic digests are generated
				{#if clientConfigQuery.data?.timezone}
					• Timezone: {clientConfigQuery.data.timezone}
				{/if}
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			{#if schedulesQuery.isPending}
				<div class="space-y-4">
					{#each [1, 2, 3] as _}
						<div class="flex items-center gap-4">
							<Skeleton class="h-10 w-24" />
							<Skeleton class="h-6 w-12" />
							<Skeleton class="h-4 flex-1" />
						</div>
					{/each}
				</div>
			{:else if schedulesQuery.data}
				{#each schedulesQuery.data as schedule}
					{@const edit = scheduleEdits[schedule.period]}
					<div class="flex flex-col gap-4 sm:flex-row sm:items-center rounded-lg border p-4">
						<div class="flex flex-wrap items-center gap-3 flex-1 min-w-0">
							<div class="w-20">
								<Label class="text-base font-medium capitalize">{schedule.period}</Label>
							</div>
							
							<Input
								type="time"
								value={edit ? formatTime(edit.hour, edit.minute) : ''}
								onchange={(e) => handleTimeChange(schedule.period, (e.target as HTMLInputElement).value)}
								class="w-28"
							/>

							<div class="flex items-center gap-2">
								<Switch
									checked={edit?.enabled ?? schedule.enabled}
									onCheckedChange={(checked) => handleEnabledChange(schedule.period, checked)}
								/>
								<span class="text-sm text-muted-foreground">
									{edit?.enabled ? 'Enabled' : 'Disabled'}
								</span>
							</div>
						</div>

						<div class="flex items-center gap-2 justify-between sm:justify-end">
							<span class="text-sm text-muted-foreground hidden lg:inline">
								Next: {formatNextRun(schedule)}
							</span>
							
							<Button
								size="sm"
								onclick={() => saveSchedule(schedule.period as DigestPeriod)}
								disabled={!hasScheduleChanged(schedule.period) || updateScheduleMutation.isPending}
							>
								{#if updateScheduleMutation.isPending}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{:else}
									<Save class="mr-2 h-4 w-4" />
								{/if}
								Save
							</Button>
						</div>
					</div>
				{/each}
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Retention Settings (Read-only) -->
	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<Settings class="h-5 w-5" />
				Retention Settings
			</Card.Title>
			<Card.Description>
				Data retention settings are configured via environment variables
			</Card.Description>
		</Card.Header>
		<Card.Content>
			{#if configQuery.isPending}
				<div class="space-y-3">
					<Skeleton class="h-4 w-48" />
					<Skeleton class="h-4 w-48" />
				</div>
			{:else if configQuery.data}
				<div class="grid gap-4 sm:grid-cols-2">
					<div class="space-y-1">
						<Label class="text-muted-foreground">Digest Retention</Label>
						<p class="font-medium">{configQuery.data.digest_retention_days} days</p>
					</div>
					<div class="space-y-1">
						<Label class="text-muted-foreground">Max Articles per Digest</Label>
						<p class="font-medium">{configQuery.data.max_articles_per_digest}</p>
					</div>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

		</Tabs.Content>
		<Tabs.Content value="security" class="mt-4 space-y-6">

	<!-- API Tokens -->
	<Card.Root>
		<Card.Header>
			<div class="flex items-center justify-between">
					<div>
						<Card.Title class="flex items-center gap-2">
							<Key class="h-5 w-5" />
							API Tokens
						</Card.Title>
						<Card.Description>
							Manage tokens for mobile apps and external integrations
						</Card.Description>
					</div>
					<div class="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
						<Button variant="outline" size="sm" onclick={openKoreaderPluginDialog}>
							<Download class="mr-2 h-4 w-4" />
							Download KOReader Plugin
						</Button>
						<Button size="sm" onclick={() => (showCreateTokenDialog = true)}>
							<Plus class="mr-2 h-4 w-4" />
							Create Token
						</Button>
					</div>
				</div>
			</Card.Header>
		<Card.Content>
			{#if tokensQuery.isPending}
				<div class="space-y-3">
					<Skeleton class="h-16 w-full" />
					<Skeleton class="h-16 w-full" />
				</div>
			{:else if tokensQuery.data && tokensQuery.data.length > 0}
				<div class="space-y-3">
					{#each tokensQuery.data as token}
						<div class="flex items-center justify-between rounded-lg border p-4">
							<div class="space-y-1">
								<p class="font-medium">{token.name}</p>
								<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
									<code class="bg-muted px-1.5 py-0.5 rounded text-xs">{token.token_prefix}</code>
									<span>Created {formatDate(token.created_at)}</span>
									<span>• {formatLastUsed(token.last_used_at)}</span>
								</div>
							</div>
							<Button
								variant="ghost"
								size="icon"
								class="text-destructive hover:text-destructive hover:bg-destructive/10"
								onclick={() => (tokenToRevoke = token)}
							>
								<Trash2 class="h-4 w-4" />
							</Button>
						</div>
					{/each}
				</div>
			{:else}
				<div class="text-center py-8 text-muted-foreground">
					<Key class="h-8 w-8 mx-auto mb-2 opacity-50" />
					<p>No API tokens yet</p>
					<p class="text-sm">Create a token to use with mobile apps or scripts</p>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Current Session -->
	<Card.Root>
		<Card.Header>
			<Card.Title>Current Session</Card.Title>
			<Card.Description>
				Your browser session token (JWT)
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			{#if $currentUser}
				<div class="flex items-center gap-4 p-3 rounded-lg bg-muted/50">
					<div class="flex-1">
						<p class="font-medium">{$currentUser.username}</p>
						<p class="text-sm text-muted-foreground">
							{$currentUser.email || 'No email set'}
							{#if $currentUser.is_admin}
								<span class="ml-2 text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">Admin</span>
							{/if}
						</p>
					</div>
				</div>
			{/if}
			<div class="flex items-center gap-2">
				<div class="relative flex-1">
					<Input
						type={showToken ? 'text' : 'password'}
						value={storedToken}
						readonly
						class="pr-20 font-mono text-xs"
					/>
					<div class="absolute right-1 top-1/2 -translate-y-1/2 flex">
						<Button
							variant="ghost"
							size="icon"
							onclick={() => (showToken = !showToken)}
							class="h-7 w-7"
						>
							{#if showToken}
								<EyeOff class="h-4 w-4" />
							{:else}
								<Eye class="h-4 w-4" />
							{/if}
						</Button>
						<Button
							variant="ghost"
							size="icon"
							onclick={copyToken}
							class="h-7 w-7"
						>
								{#if copiedToken}
									<CheckCircle2 class="h-4 w-4 text-success" />
								{:else}
									<Copy class="h-4 w-4" />
								{/if}
						</Button>
					</div>
				</div>
			</div>
			<p class="text-sm text-muted-foreground">
				This JWT is stored in your browser and expires in 7 days.
			</p>
		</Card.Content>
	</Card.Root>

		</Tabs.Content>
		<Tabs.Content value="integrations" class="mt-4 space-y-6">

	<!-- Integrations -->
	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<Plug class="h-5 w-5" />
				Integrations
			</Card.Title>
			<Card.Description>
				Configure external service integrations
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-3">
			<!-- Wallabag -->
			<div class="rounded-lg border">
				<div class="flex items-center justify-between gap-2 p-3">
					<button
						type="button"
						class="min-w-0 flex-1 rounded-md px-1 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
						onclick={() => (wallabagExpanded = !wallabagExpanded)}
						aria-expanded={wallabagExpanded}
					>
						<p class="font-medium">Wallabag</p>
						<p class="text-sm text-muted-foreground">Read-it-later integration</p>
					</button>
					<div class="flex items-center gap-2">
						{#if wallabagConfigQuery.data}
							<Switch
								checked={wbEnabled}
								aria-label="Enable Wallabag integration"
								onCheckedChange={(checked) => {
									wbEnabled = checked;
									updateWallabagMutation.mutate({ enabled: checked });
								}}
							/>
						{/if}
						{#if clientConfigQuery.data?.wallabag?.enabled}
							<CheckCircle2 class="h-5 w-5 text-success" />
						{/if}
						<Button
							type="button"
							variant="ghost"
							size="icon-sm"
							onclick={() => (wallabagExpanded = !wallabagExpanded)}
							aria-label={wallabagExpanded ? 'Collapse Wallabag settings' : 'Expand Wallabag settings'}
						>
							{#if wallabagExpanded}
								<ChevronUp class="h-4 w-4 text-muted-foreground" />
							{:else}
								<ChevronDown class="h-4 w-4 text-muted-foreground" />
							{/if}
						</Button>
					</div>
				</div>

				{#if wallabagExpanded}
					<div class="border-t p-4 space-y-4">
						{#if wallabagConfigQuery.isPending}
							<div class="space-y-3">
								<Skeleton class="h-10 w-full" />
								<Skeleton class="h-10 w-full" />
							</div>
						{:else}
							<div class="grid gap-4 sm:grid-cols-2">
								<div class="space-y-2 sm:col-span-2">
									<Label for="wb-url">URL</Label>
									<Input
										id="wb-url"
										placeholder="https://wallabag.example.com"
										bind:value={wbForm.url}
									/>
								</div>
								<div class="space-y-2">
									<Label for="wb-client-id">Client ID</Label>
									<Input id="wb-client-id" bind:value={wbForm.client_id} />
								</div>
								<div class="space-y-2">
									<Label for="wb-client-secret">Client Secret</Label>
									<Input id="wb-client-secret" type="password" bind:value={wbForm.client_secret} />
								</div>
								<div class="space-y-2">
									<Label for="wb-username">Username</Label>
									<Input id="wb-username" bind:value={wbForm.username} />
								</div>
								<div class="space-y-2">
									<Label for="wb-password">Password</Label>
									<Input id="wb-password" type="password" bind:value={wbForm.password} />
								</div>
								<div class="space-y-2">
									<Label for="wb-mode">Processing Mode</Label>
									<select
										id="wb-mode"
										class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
										bind:value={wbForm.mode}
									>
										<option value="raw">Raw (full text)</option>
										<option value="summarize">Summarize (AI)</option>
									</select>
								</div>
								<div class="space-y-2">
									<Label for="wb-max">Max Articles</Label>
									<Input
										id="wb-max"
										type="number"
										min="1"
										bind:value={wbForm.max_articles}
									/>
								</div>
								<div class="space-y-2 sm:col-span-2">
									<Label for="wb-tag">Tag on Process</Label>
									<Input
										id="wb-tag"
										placeholder="ghostwriter"
										bind:value={wbForm.tag_on_process}
									/>
								</div>
							</div>

							<div class="flex flex-wrap items-center gap-2 pt-2">
								<Button
									variant="outline"
									size="sm"
									onclick={() => testWallabagMutation.mutate()}
									disabled={testWallabagMutation.isPending}
								>
									{#if testWallabagMutation.isPending}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{:else}
										<TestTube2 class="mr-2 h-4 w-4" />
									{/if}
									Test Connection
								</Button>
								<Button
									size="sm"
									onclick={saveWallabag}
									disabled={!hasWallabagChanged() || updateWallabagMutation.isPending}
								>
									{#if updateWallabagMutation.isPending}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{:else}
										<Save class="mr-2 h-4 w-4" />
									{/if}
									Save
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => previewWallabagMutation.mutate()}
									disabled={previewWallabagMutation.isPending}
								>
									{#if previewWallabagMutation.isPending}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{:else}
										<Search class="mr-2 h-4 w-4" />
									{/if}
									Preview
								</Button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => clearWallabagSeenMutation.mutate()}
									disabled={clearWallabagSeenMutation.isPending}
								>
									{#if clearWallabagSeenMutation.isPending}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{:else}
										<Trash2 class="mr-2 h-4 w-4" />
									{/if}
									Clear History
								</Button>
							</div>

							{#if wallabagPreview?.status === 'ok' && wallabagPreview.articles.length > 0}
								<div class="mt-3 rounded-md border p-3">
									<p class="mb-2 text-sm font-medium">{wallabagPreview.count} unread article{wallabagPreview.count === 1 ? '' : 's'}</p>
									<ul class="space-y-1">
										{#each wallabagPreview.articles as article}
											<li class="text-sm break-words">
												<a href={article.url} target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">{article.title}</a>
												<span class="text-muted-foreground">
													{#if article.author} — {article.author}{/if}
													{#if article.word_count} ({article.word_count.toLocaleString()} words){/if}
												</span>
											</li>
										{/each}
									</ul>
								</div>
							{:else if wallabagPreview?.status === 'ok' && wallabagPreview.articles.length === 0}
								<p class="mt-3 text-sm text-muted-foreground">No unread articles found.</p>
							{/if}
						{/if}
					</div>
				{/if}
			</div>

			<!-- Gmail Newsletters -->
			<div class="rounded-lg border p-3">
				<div class="flex flex-wrap items-center justify-between gap-2">
					<div>
						<p class="font-medium">Gmail Newsletters</p>
						<p class="text-sm text-muted-foreground">
							{clientConfigQuery.data?.newsletters?.label
								? `Label: ${clientConfigQuery.data.newsletters.label}`
								: 'Newsletter email integration'}
						</p>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<Switch
							checked={clientConfigQuery.data?.newsletters?.enabled ?? false}
							onCheckedChange={(checked) => {
								updateClientConfigMutation.mutate({ newsletters_enabled: checked });
							}}
						/>
							{#if clientConfigQuery.data?.newsletters?.enabled}
								<CheckCircle2 class="h-5 w-5 text-success" />
							<Button
								variant="outline"
								size="sm"
								onclick={() => previewNewsletterMutation.mutate()}
								disabled={previewNewsletterMutation.isPending}
							>
								{#if previewNewsletterMutation.isPending}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{:else}
									<Search class="mr-2 h-4 w-4" />
								{/if}
								Preview
							</Button>
							<Button
								variant="outline"
								size="sm"
								onclick={() => clearNewsletterSeenMutation.mutate()}
								disabled={clearNewsletterSeenMutation.isPending}
							>
								{#if clearNewsletterSeenMutation.isPending}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{:else}
									<Trash2 class="mr-2 h-4 w-4" />
								{/if}
								Clear History
							</Button>
						{:else}
							<a href="/newsletters" class="text-sm text-primary hover:underline">
								Configure
							</a>
						{/if}
					</div>
				</div>

				{#if newsletterPreview?.status === 'ok' && newsletterPreview.articles.length > 0}
					<div class="mt-3 rounded-md border p-3">
						<p class="mb-2 text-sm font-medium">{newsletterPreview.count} newsletter{newsletterPreview.count === 1 ? '' : 's'}</p>
						<ul class="space-y-1">
							{#each newsletterPreview.articles as article}
								<li class="text-sm">
									<a href={article.url} target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">{article.title}</a>
									<span class="text-muted-foreground">
										{#if article.author} — {article.author}{/if}
										{#if article.word_count} ({article.word_count.toLocaleString()} words){/if}
									</span>
								</li>
							{/each}
						</ul>
					</div>
				{:else if newsletterPreview?.status === 'ok' && newsletterPreview.articles.length === 0}
					<p class="mt-3 text-sm text-muted-foreground">No newsletters found.</p>
				{/if}
			</div>
		</Card.Content>
	</Card.Root>

	<!-- Transcription -->
	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<FileText class="h-5 w-5" />
				Transcription
			</Card.Title>
			<Card.Description>
				Configure audio transcription for YouTube videos and podcast episodes
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			<div class="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
				<div class="space-y-1">
					<p class="font-medium">Transcription Provider</p>
					<p class="text-sm text-muted-foreground">
						Choose how audio content is transcribed to text.
					</p>
				</div>
				<div class="flex items-center gap-3">
					<select
						class="flex h-10 w-48 rounded-md border border-input bg-background px-3 py-2 text-sm"
						bind:value={whisperProvider}
					>
						<option value="local">Local whisper.cpp</option>
						<option value="openai">OpenAI Whisper API</option>
						<option value="auto">Auto (local, then OpenAI)</option>
					</select>
					<Button
						size="sm"
						onclick={saveWhisperProvider}
						disabled={updateClientConfigMutation.isPending || whisperProvider === (clientConfigQuery.data?.whisper_provider ?? 'local')}
					>
						{#if updateClientConfigMutation.isPending}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{:else}
							<Save class="mr-2 h-4 w-4" />
						{/if}
						Save
					</Button>
				</div>
			</div>

			<div class="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
				<div class="space-y-1">
					<p class="font-medium">Transcription Timeout</p>
					<p class="text-sm text-muted-foreground">
						Maximum time allowed for audio transcription (1–120 minutes).
					</p>
				</div>
				<div class="flex items-center gap-3">
					<div class="flex items-center gap-2">
						<Input
							type="number"
							min={1}
							max={120}
							bind:value={whisperTimeout}
							class="w-20"
						/>
						<span class="text-sm text-muted-foreground">min</span>
					</div>
					<Button
						size="sm"
						onclick={saveWhisperTimeout}
						disabled={updateClientConfigMutation.isPending || whisperTimeout === (clientConfigQuery.data?.whisper_timeout_minutes ?? 30)}
					>
						{#if updateClientConfigMutation.isPending}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{:else}
							<Save class="mr-2 h-4 w-4" />
						{/if}
						Save
					</Button>
				</div>
			</div>

			{#if whisperProvider === 'openai' || whisperProvider === 'auto'}
				<div class="flex items-center gap-2 rounded-lg border p-4">
					<div class="space-y-1 flex-1">
						<p class="font-medium">OpenAI Whisper API</p>
						<p class="text-sm text-muted-foreground">
							Uses the OPENAI_API_KEY environment variable configured on the server.
						</p>
					</div>
						{#if configQuery.data?.ai_provider === 'openai'}
							<CheckCircle2 class="h-5 w-5 text-success" />
						{:else}
							<AlertTriangle class="h-5 w-5 text-warning" />
							<span class="text-sm text-muted-foreground">Key not configured</span>
						{/if}
				</div>
			{/if}

			{#if whisperProvider === 'local' || whisperProvider === 'auto'}
				<div class="flex flex-col gap-3 rounded-lg border p-4">
					<div class="space-y-1">
						<p class="font-medium">Whisper.cpp Models</p>
						<p class="text-sm text-muted-foreground">
							Download a model to enable local audio transcription.
						</p>
					</div>

					{#if whisperModelsQuery.isPending}
						<div class="space-y-2">
							<Skeleton class="h-4 w-40" />
							<Skeleton class="h-10 w-full" />
						</div>
					{:else if whisperModelsQuery.data}
						<div class="space-y-2">
							{#each whisperModelsQuery.data.models as model}
								<div class="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
									<div class="space-y-1">
										<div class="flex items-center gap-2">
											<p class="font-medium">{model.name}</p>
											{#if whisperModelsQuery.data.active_model === model.name}
												<span class="rounded-full bg-muted px-2 py-0.5 text-xs">Active</span>
											{/if}
										</div>
										<p class="text-xs text-muted-foreground">
											{#if model.status === 'downloaded'}
												Downloaded{#if model.size_bytes} • {formatFileSize(model.size_bytes)}{/if}
											{:else if model.status === 'downloading'}
												Downloading{#if getDownloadProgress(model)} • {getDownloadProgress(model)}{/if}
											{:else if model.status === 'failed'}
												Download failed
											{:else}
												Not downloaded
											{/if}
										</p>
										{#if model.error}
											<p class="text-xs text-destructive">{model.error}</p>
										{/if}
									</div>

									<div class="flex items-center gap-2">
										{#if model.status === 'downloaded'}
											{#if whisperModelsQuery.data.active_model !== model.name}
												<Button
													variant="outline"
													size="sm"
													onclick={() => setActiveWhisperModelMutation.mutate(model.name)}
													disabled={setActiveWhisperModelMutation.isPending}
												>
													Use
												</Button>
											{/if}
											<Button
												variant="outline"
												size="sm"
												onclick={() => deleteWhisperModelMutation.mutate(model.name)}
												disabled={deleteWhisperModelMutation.isPending}
											>
												<Trash2 class="mr-2 h-4 w-4" />
												Remove
											</Button>
										{:else if model.status === 'downloading'}
											<Button variant="outline" size="sm" disabled>
												<Loader2 class="mr-2 h-4 w-4 animate-spin" />
												Downloading
											</Button>
										{:else}
											<Button
												size="sm"
												onclick={() => downloadWhisperModelMutation.mutate(model.name)}
												disabled={downloadWhisperModelMutation.isPending}
											>
												<Download class="mr-2 h-4 w-4" />
												Download
											</Button>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{:else}
						<p class="text-sm text-muted-foreground">Unable to load model status.</p>
					{/if}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

		</Tabs.Content>
		<Tabs.Content value="logs" class="mt-4 space-y-6">
			<!-- Activity Logs -->
			<Card.Root>
				<Card.Header>
					<Card.Title class="flex items-center gap-2">
						<FileText class="h-5 w-5" />
						Activity Logs
					</Card.Title>
					<Card.Description>Download server log files for debugging</Card.Description>
				</Card.Header>
				<Card.Content>
					{#if logFilesQuery.isPending}
						<div class="space-y-2">
							<Skeleton class="h-10 w-full" />
							<Skeleton class="h-10 w-full" />
						</div>
					{:else if logFilesQuery.data && logFilesQuery.data.length > 0}
						<div class="space-y-2">
							{#each logFilesQuery.data as logFile}
								<div class="flex items-center justify-between rounded-lg border p-3">
									<div>
										<p class="text-sm font-medium">{logFile.filename}</p>
										<p class="text-xs text-muted-foreground">{formatFileSize(logFile.size_bytes)}</p>
									</div>
									<Button
										variant="outline"
										size="sm"
										onclick={() => downloadLog(logFile.filename)}
									>
										<Download class="mr-2 h-4 w-4" />
										Download
									</Button>
								</div>
							{/each}
						</div>
					{:else}
						<div class="py-8 text-center text-muted-foreground">
							<FileText class="mx-auto mb-2 h-8 w-8 opacity-50" />
							<p>No log files available</p>
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		</Tabs.Content>
	</Tabs.Root>
</div>

<!-- KOReader Plugin Download Dialog -->
<Dialog.Root bind:open={showKoreaderPluginDialog}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title class="flex items-center gap-2">
				<Download class="h-5 w-5" />
				Download KOReader Plugin
			</Dialog.Title>
			<Dialog.Description>
				Create a preconfigured plugin zip with your server URL and a newly generated API token.
			</Dialog.Description>
		</Dialog.Header>
		<form
			onsubmit={(e) => {
				e.preventDefault();
				downloadKoreaderPlugin();
			}}
			class="space-y-4"
		>
			<div class="space-y-2">
				<Label for="koreader-token-name">Token Name</Label>
				<Input
					id="koreader-token-name"
					placeholder="KOReader Plugin"
					bind:value={koreaderPluginTokenName}
					disabled={downloadKoreaderPluginMutation.isPending}
				/>
			</div>
			<div class="space-y-2">
				<Label for="koreader-server-url">Server URL</Label>
				<Input
					id="koreader-server-url"
					placeholder="https://ghostwriter.example.com"
					bind:value={koreaderPluginServerUrl}
					disabled={downloadKoreaderPluginMutation.isPending}
				/>
				<p class="text-xs text-muted-foreground">
					Leave as-is unless KOReader will connect through a different public URL.
				</p>
			</div>
			<div class="rounded-lg border border-warning/30 bg-warning/10 p-3">
				<div class="flex items-start gap-2">
					<AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-warning" />
					<p class="text-xs text-warning/90">
						Keep the downloaded plugin zip private. It includes a live API token tied to your account.
					</p>
				</div>
			</div>
			<Dialog.Footer>
				<Button
					type="button"
					variant="outline"
					onclick={() => (showKoreaderPluginDialog = false)}
					disabled={downloadKoreaderPluginMutation.isPending}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					disabled={!koreaderPluginTokenName.trim() || downloadKoreaderPluginMutation.isPending}
				>
					{#if downloadKoreaderPluginMutation.isPending}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Download Plugin
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<!-- Create Token Dialog -->
<Dialog.Root bind:open={showCreateTokenDialog}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Create API Token</Dialog.Title>
			<Dialog.Description>
				Give your token a descriptive name (e.g., "My iPhone", "Home Server")
			</Dialog.Description>
		</Dialog.Header>
		<form
			onsubmit={(e) => {
				e.preventDefault();
				if (newTokenName.trim()) {
					createTokenMutation.mutate(newTokenName.trim());
				}
			}}
			class="space-y-4"
		>
			<div class="space-y-2">
				<Label for="token-name">Token Name</Label>
				<Input
					id="token-name"
					placeholder="My iPhone"
					bind:value={newTokenName}
					disabled={createTokenMutation.isPending}
				/>
			</div>
			<Dialog.Footer>
				<Button type="button" variant="outline" onclick={() => (showCreateTokenDialog = false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={!newTokenName.trim() || createTokenMutation.isPending}>
					{#if createTokenMutation.isPending}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Create Token
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<!-- New Token Display Dialog -->
<Dialog.Root bind:open={showNewTokenDialog}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
				<Dialog.Title class="flex items-center gap-2">
					<CheckCircle2 class="h-5 w-5 text-success" />
					Token Created
				</Dialog.Title>
			<Dialog.Description>
				Copy this token now — you won't be able to see it again!
			</Dialog.Description>
		</Dialog.Header>
		<div class="space-y-4">
				<div class="rounded-lg border border-warning/30 bg-warning/10 p-4">
					<div class="flex items-start gap-2">
						<AlertTriangle class="mt-0.5 h-5 w-5 shrink-0 text-warning" />
						<p class="text-sm text-warning/90">
							This is the only time you'll see this token. Store it somewhere safe!
						</p>
					</div>
				</div>
			<div class="flex items-center gap-2">
				<Input
					type="text"
					value={newlyCreatedToken}
					readonly
					class="font-mono text-sm"
				/>
				<Button variant="outline" size="icon" onclick={copyNewToken}>
						{#if copiedNewToken}
							<CheckCircle2 class="h-4 w-4 text-success" />
						{:else}
							<Copy class="h-4 w-4" />
						{/if}
				</Button>
			</div>
		</div>
		<Dialog.Footer>
			<Button
				onclick={() => {
					showNewTokenDialog = false;
					newlyCreatedToken = '';
				}}
			>
				Done
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<!-- Revoke Token Confirmation -->
<AlertDialog.Root open={tokenToRevoke !== null}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Revoke API Token?</AlertDialog.Title>
			<AlertDialog.Description>
				This will permanently revoke the token "{tokenToRevoke?.name}". Any apps or scripts using this token will stop working immediately.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel onclick={() => (tokenToRevoke = null)}>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action
				class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
				onclick={() => tokenToRevoke && revokeTokenMutation.mutate(tokenToRevoke.id)}
			>
				{#if revokeTokenMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Revoke Token
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
