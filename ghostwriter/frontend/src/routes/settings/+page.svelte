<script lang="ts">
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api, type Schedule, type ScheduleUpdate, type DigestPeriod, type APITokenResponse, type LogFileInfo } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Switch } from '$lib/components/ui/switch';
	import { Skeleton } from '$lib/components/ui/skeleton';
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
		Download
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

	function parseUTC(dateStr: string): Date {
		if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
			return new Date(dateStr + 'Z');
		}
		return new Date(dateStr);
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

	function formatDate(dateStr: string): string {
		return parseUTC(dateStr).toLocaleDateString('en-US', {
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
</script>

<svelte:head>
	<title>Settings - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Settings</h1>
		<p class="text-muted-foreground">Configure your Ghostwriter instance</p>
	</div>

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
						<div class="flex items-center gap-4 flex-1 min-w-0">
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
				<Button size="sm" onclick={() => (showCreateTokenDialog = true)}>
					<Plus class="mr-2 h-4 w-4" />
					Create Token
				</Button>
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
								<div class="flex items-center gap-3 text-sm text-muted-foreground">
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
								<CheckCircle2 class="h-4 w-4 text-green-500" />
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

	<!-- Integrations Status -->
	<Card.Root>
		<Card.Header>
			<Card.Title>Integrations</Card.Title>
			<Card.Description>
				Status of external service integrations
			</Card.Description>
		</Card.Header>
		<Card.Content>
			{#if clientConfigQuery.isPending}
				<div class="space-y-3">
					<Skeleton class="h-8 w-full" />
					<Skeleton class="h-8 w-full" />
				</div>
			{:else if clientConfigQuery.data}
				<div class="space-y-3">
					<div class="flex items-center justify-between rounded-lg border p-3">
						<div>
							<p class="font-medium">Wallabag</p>
							<p class="text-sm text-muted-foreground">Read-it-later integration</p>
						</div>
						<div class="flex items-center gap-2">
							{#if clientConfigQuery.data.wallabag?.enabled}
								<CheckCircle2 class="h-5 w-5 text-green-500" />
								<span class="text-sm text-green-600">Connected</span>
							{:else}
								<span class="text-sm text-muted-foreground">Not configured</span>
							{/if}
						</div>
					</div>

					<div class="flex items-center justify-between rounded-lg border p-3">
						<div>
							<p class="font-medium">Gmail Newsletters</p>
							<p class="text-sm text-muted-foreground">
								{clientConfigQuery.data.newsletters?.label
									? `Label: ${clientConfigQuery.data.newsletters.label}`
									: 'Newsletter email integration'}
							</p>
						</div>
						<div class="flex items-center gap-2">
							{#if clientConfigQuery.data.newsletters?.enabled}
								<CheckCircle2 class="h-5 w-5 text-green-500" />
								<span class="text-sm text-green-600">Connected</span>
							{:else}
								<a href="/newsletters" class="text-sm text-primary hover:underline">
									Configure
								</a>
							{/if}
						</div>
					</div>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>

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
				<CheckCircle2 class="h-5 w-5 text-green-500" />
				Token Created
			</Dialog.Title>
			<Dialog.Description>
				Copy this token now — you won't be able to see it again!
			</Dialog.Description>
		</Dialog.Header>
		<div class="space-y-4">
			<div class="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg">
				<div class="flex items-start gap-2">
					<AlertTriangle class="h-5 w-5 text-amber-600 dark:text-amber-500 shrink-0 mt-0.5" />
					<p class="text-sm text-amber-800 dark:text-amber-200">
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
						<CheckCircle2 class="h-4 w-4 text-green-500" />
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
								onclick={() => window.open(api.getLogDownloadUrl(logFile.filename), '_blank')}
							>
								<Download class="mr-2 h-4 w-4" />
								Download
							</Button>
						</div>
					{/each}
				</div>
			{:else}
				<div class="text-center py-8 text-muted-foreground">
					<FileText class="h-8 w-8 mx-auto mb-2 opacity-50" />
					<p>No log files available</p>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

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
