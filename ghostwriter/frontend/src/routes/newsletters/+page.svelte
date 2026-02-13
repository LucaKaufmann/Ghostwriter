<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { createQuery, useQueryClient } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { toast } from 'svelte-sonner';
	import {
		AlertCircle,
		CheckCircle2,
		ExternalLink,
		Inbox,
		Mail,
		RefreshCw,
		Shield,
		Unplug
	} from 'lucide-svelte';

	const queryClient = useQueryClient();

	let connectInProgress = $state(false);

	const statusQuery = createQuery(() => ({
		queryKey: ['newsletters', 'status'],
		queryFn: () => api.getNewsletterStatus()
	}));

	function handleFocus() {
		queryClient.invalidateQueries({ queryKey: ['newsletters', 'status'] });
	}

	onMount(() => {
		window.addEventListener('focus', handleFocus);
	});

	onDestroy(() => {
		window.removeEventListener('focus', handleFocus);
	});

	async function refreshStatus() {
		await statusQuery.refetch();
	}

	function handleConnect() {
		const oauthWindow = window.open(api.getOAuthStartUrl(), '_blank', 'width=600,height=700');
		if (!oauthWindow) {
			toast.error('Popup blocked', {
				description: 'Allow popups for this site and try connecting again.'
			});
			return;
		}
		oauthWindow.focus();
		connectInProgress = true;
		toast.message('OAuth window opened', {
			description: 'Complete authorization, then return to refresh connection status.'
		});
	}
</script>

<svelte:head>
	<title>Newsletters - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Newsletters</h1>
			<p class="text-muted-foreground">Connect Gmail and include labeled newsletters in your digests</p>
		</div>
		<Button variant="outline" size="sm" onclick={refreshStatus} disabled={statusQuery.isFetching}>
			<RefreshCw class="mr-2 h-4 w-4 {statusQuery.isFetching ? 'animate-spin' : ''}" />
			Refresh Status
		</Button>
	</div>

	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<Mail class="h-5 w-5" />
				Gmail Integration
			</Card.Title>
			<Card.Description>
				Connect Gmail once, then label newsletters to include them in future digests.
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			{#if statusQuery.isPending}
				<div class="space-y-3">
					<Skeleton class="h-16 w-full" />
					<Skeleton class="h-10 w-40" />
				</div>
			{:else if statusQuery.isError}
				<div class="rounded-lg border border-destructive/30 bg-destructive/10 p-4">
					<div class="flex items-start gap-3">
						<AlertCircle class="mt-0.5 h-5 w-5 text-destructive" />
						<div class="space-y-2">
							<p class="font-medium text-destructive">Could not load newsletter status</p>
							<p class="text-sm text-destructive/90">
								{statusQuery.error instanceof Error ? statusQuery.error.message : 'Unknown error'}
							</p>
							<Button variant="outline" size="sm" onclick={refreshStatus}>Try Again</Button>
						</div>
					</div>
				</div>
			{:else if statusQuery.data?.configured}
				<div class="space-y-4">
					<div class="rounded-lg border border-success/30 bg-success/10 p-4">
						<div class="flex items-start gap-3">
							<CheckCircle2 class="mt-0.5 h-5 w-5 text-success" />
							<div>
								<p class="font-medium text-success">Connected and ready</p>
								<p class="text-sm text-success/90">
									Labeled Gmail messages will be included in upcoming digest runs.
								</p>
							</div>
						</div>
					</div>

					<div class="rounded-lg border p-4">
						<div class="flex flex-wrap items-center gap-2">
							<span class="text-sm text-muted-foreground">Processing label</span>
							<Badge variant="secondary">{statusQuery.data.label}</Badge>
						</div>
						<p class="mt-2 text-sm text-muted-foreground">
							Only messages with this label are imported for newsletters.
						</p>
					</div>

					<div class="flex flex-wrap gap-2">
						<Button onclick={handleConnect}>
							<ExternalLink class="mr-2 h-4 w-4" />
							Reconnect Gmail
						</Button>
						<a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">
							<Button variant="outline">
								<Shield class="mr-2 h-4 w-4" />
								Google Permissions
							</Button>
						</a>
					</div>
				</div>
			{:else if statusQuery.data?.oauth_ready}
				<div class="space-y-4">
					<div class="rounded-lg border border-warning/30 bg-warning/10 p-4">
						<div class="flex items-start gap-3">
							<AlertCircle class="mt-0.5 h-5 w-5 text-warning" />
							<div>
								<p class="font-medium text-warning">Gmail is not connected yet</p>
								<p class="text-sm text-warning/90">
									OAuth is configured. Finish one authorization step to start importing newsletters.
								</p>
							</div>
						</div>
					</div>

					{#if connectInProgress}
						<div class="rounded-lg border border-info/30 bg-info/10 p-4">
							<div class="flex items-start gap-3">
								<Mail class="mt-0.5 h-5 w-5 text-info" />
								<div>
									<p class="font-medium text-info">Authorization in progress</p>
									<p class="text-sm text-info/90">
										After approving access in the popup, return here and click "Refresh Status".
									</p>
								</div>
							</div>
						</div>
					{/if}

					<div class="flex flex-wrap gap-2">
						<Button onclick={handleConnect}>
							<Mail class="mr-2 h-4 w-4" />
							Connect Gmail
						</Button>
						<Button variant="outline" onclick={refreshStatus}>I finished OAuth</Button>
					</div>
				</div>
			{:else}
				<div class="rounded-lg border border-muted p-4">
					<div class="flex items-start gap-3">
						<Unplug class="mt-0.5 h-5 w-5 text-muted-foreground" />
						<div class="space-y-2">
							<p class="font-medium">Integration not configured on server</p>
							<p class="text-sm text-muted-foreground">
								Gmail OAuth credentials are missing. Add server OAuth settings, then refresh this page.
							</p>
						</div>
					</div>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Title>Setup Flow</Card.Title>
		</Card.Header>
		<Card.Content class="grid gap-4 md:grid-cols-3">
			<div class="rounded-lg border p-4">
				<p class="text-sm font-semibold">1. Connect Gmail</p>
				<p class="mt-2 text-sm text-muted-foreground">Authorize Ghostwriter to read labeled newsletter messages.</p>
			</div>
			<div class="rounded-lg border p-4">
				<p class="text-sm font-semibold">2. Apply label</p>
				<p class="mt-2 text-sm text-muted-foreground">
					Use the <span class="font-medium">{statusQuery.data?.label || 'Ghostwriter'}</span> label in Gmail filters.
				</p>
			</div>
			<div class="rounded-lg border p-4">
				<p class="text-sm font-semibold">3. Run digest</p>
				<p class="mt-2 text-sm text-muted-foreground">Labeled emails are merged into generated digest content.</p>
			</div>
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Title>Troubleshooting</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-3 text-sm text-muted-foreground">
			<p>If OAuth keeps failing, first disconnect/reconnect from Google account permissions, then connect again here.</p>
			<p>If status never changes, click "Refresh Status" after returning from the OAuth popup window.</p>
			<p>
				If messages are missing, verify the Gmail label exists and is applied to the newsletters you expect.
			</p>
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Title>Privacy</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-2 text-sm text-muted-foreground">
			<div class="flex items-start gap-2">
				<Inbox class="mt-0.5 h-4 w-4" />
				<p>Only messages with the configured label are read.</p>
			</div>
			<div class="flex items-start gap-2">
				<Shield class="mt-0.5 h-4 w-4" />
				<p>Processing runs on your Ghostwriter server with your configured summarization provider.</p>
			</div>
		</Card.Content>
	</Card.Root>
</div>
