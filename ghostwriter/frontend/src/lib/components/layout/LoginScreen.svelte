<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Card from '$lib/components/ui/card';
	import ThemeToggle from '$lib/components/layout/ThemeToggle.svelte';
	import { auth, authError, serverStatus, authStatus } from '$lib/stores/auth';
	import { BookOpen, Loader2, AlertCircle, CheckCircle2, UserPlus, LogIn } from 'lucide-svelte';

	let username = $state('');
	let password = $state('');
	let confirmPassword = $state('');
	let email = $state('');
	let isSubmitting = $state(false);
	let showLegacyTokenInput = $state(false);
	let legacyToken = $state('');

	// Derived: are we in registration mode?
	const isRegistration = $derived($authStatus?.registration_open ?? false);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (!username.trim() || !password.trim()) return;

		if (isRegistration) {
			// Validate password match
			if (password !== confirmPassword) {
				// Set error via store or local state
				return;
			}
		}

		isSubmitting = true;
		console.log('[login] submitting, isRegistration:', isRegistration);

		let success: boolean;
		if (isRegistration) {
			success = await auth.register(username.trim(), password, email.trim() || undefined);
		} else {
			success = await auth.loginWithCredentials(username.trim(), password);
		}

		console.log('[login] result:', success);
		isSubmitting = false;

		if (success) {
			username = '';
			password = '';
			confirmPassword = '';
			email = '';
		}
	}

	async function handleLegacyToken(e: Event) {
		e.preventDefault();
		if (!legacyToken.trim()) return;

		isSubmitting = true;
		const success = await auth.loginWithToken(legacyToken.trim());
		isSubmitting = false;

		if (success) {
			legacyToken = '';
		}
	}

	// Password validation
	const passwordsMatch = $derived(password === confirmPassword);
	const passwordLongEnough = $derived(password.length >= 8);
	const canSubmitRegistration = $derived(
		username.trim().length >= 3 &&
			passwordLongEnough &&
			passwordsMatch
	);
	const canSubmitLogin = $derived(username.trim() && password.trim());
</script>

<div class="flex min-h-screen items-center justify-center bg-background p-4">
	<div class="w-full max-w-md">
		<div class="mb-4 flex justify-end">
			<ThemeToggle />
		</div>
		<div class="mb-8 text-center">
			<div
				class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10"
			>
				<BookOpen class="h-8 w-8 text-primary" />
			</div>
			<h1 class="text-2xl font-bold">Ghostwriter</h1>
			<p class="text-muted-foreground">Your personal news digest generator</p>
		</div>

		{#if !showLegacyTokenInput}
			<Card.Root>
				<Card.Header>
					<Card.Title class="flex items-center gap-2">
						{#if isRegistration}
							<UserPlus class="h-5 w-5" />
							Create Admin Account
						{:else}
							<LogIn class="h-5 w-5" />
							Welcome Back
						{/if}
					</Card.Title>
					<Card.Description>
						{#if isRegistration}
							Set up your Ghostwriter instance by creating the admin account
						{:else}
							Sign in to access your dashboard
						{/if}
					</Card.Description>
				</Card.Header>
				<Card.Content>
					<form onsubmit={handleSubmit} class="space-y-4">
						<div class="space-y-2">
							<Label for="username">Username</Label>
							<Input
								id="username"
								type="text"
								placeholder="Enter username"
								bind:value={username}
								disabled={isSubmitting}
								autocomplete="username"
								minlength={3}
							/>
						</div>

						{#if isRegistration}
							<div class="space-y-2">
								<Label for="email">Email (optional)</Label>
								<Input
									id="email"
									type="email"
									placeholder="admin@example.com"
									bind:value={email}
									disabled={isSubmitting}
									autocomplete="email"
								/>
							</div>
						{/if}

						<div class="space-y-2">
							<Label for="password">Password</Label>
							<Input
								id="password"
								type="password"
								placeholder={isRegistration ? 'At least 8 characters' : 'Enter password'}
								bind:value={password}
								disabled={isSubmitting}
								autocomplete={isRegistration ? 'new-password' : 'current-password'}
							/>
							{#if isRegistration && password && !passwordLongEnough}
								<p class="text-xs text-destructive">Password must be at least 8 characters</p>
							{/if}
						</div>

						{#if isRegistration}
							<div class="space-y-2">
								<Label for="confirmPassword">Confirm Password</Label>
								<Input
									id="confirmPassword"
									type="password"
									placeholder="Confirm your password"
									bind:value={confirmPassword}
									disabled={isSubmitting}
									autocomplete="new-password"
								/>
								{#if confirmPassword && !passwordsMatch}
									<p class="text-xs text-destructive">Passwords don't match</p>
								{/if}
							</div>
						{/if}

						{#if $authError}
							<div class="flex items-center gap-2 text-sm text-destructive">
								<AlertCircle class="h-4 w-4" />
								<span>{$authError}</span>
							</div>
						{/if}

						<Button
							type="submit"
							class="w-full"
							disabled={isSubmitting || (isRegistration ? !canSubmitRegistration : !canSubmitLogin)}
						>
							{#if isSubmitting}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								{isRegistration ? 'Creating Account...' : 'Signing In...'}
							{:else if isRegistration}
								<UserPlus class="mr-2 h-4 w-4" />
								Create Account
							{:else}
								<LogIn class="mr-2 h-4 w-4" />
								Sign In
							{/if}
						</Button>
					</form>
				</Card.Content>
				<Card.Footer class="flex-col gap-2 text-sm text-muted-foreground">
					{#if $serverStatus}
						<div class="flex items-center gap-2 text-green-600">
							<CheckCircle2 class="h-4 w-4" />
							<span>Server online • v{$serverStatus.version}</span>
						</div>
					{:else}
						<div class="flex items-center gap-2 text-destructive">
							<AlertCircle class="h-4 w-4" />
							<span>Cannot connect to server</span>
						</div>
					{/if}

					{#if !isRegistration}
						<button
							type="button"
							class="text-xs text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
							onclick={() => (showLegacyTokenInput = true)}
						>
							Use legacy API token instead
						</button>
					{/if}
				</Card.Footer>
			</Card.Root>
		{:else}
			<!-- Legacy API Token Input -->
			<Card.Root>
				<Card.Header>
					<Card.Title>Legacy API Token</Card.Title>
					<Card.Description>
						Enter your API token from the API_KEY environment variable
					</Card.Description>
				</Card.Header>
				<Card.Content>
					<form onsubmit={handleLegacyToken} class="space-y-4">
						<div class="space-y-2">
							<Label for="token">API Token</Label>
							<Input
								id="token"
								type="password"
								placeholder="Enter your API token"
								bind:value={legacyToken}
								disabled={isSubmitting}
								autocomplete="off"
							/>
						</div>

						{#if $authError}
							<div class="flex items-center gap-2 text-sm text-destructive">
								<AlertCircle class="h-4 w-4" />
								<span>{$authError}</span>
							</div>
						{/if}

						<Button type="submit" class="w-full" disabled={isSubmitting || !legacyToken.trim()}>
							{#if isSubmitting}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								Connecting...
							{:else}
								Connect
							{/if}
						</Button>
					</form>
				</Card.Content>
				<Card.Footer class="flex-col gap-2 text-sm text-muted-foreground">
					<button
						type="button"
						class="text-xs text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
						onclick={() => {
							showLegacyTokenInput = false;
							auth.clearError();
						}}
					>
						← Back to username login
					</button>
				</Card.Footer>
			</Card.Root>
		{/if}

		<p class="mt-4 text-center text-xs text-muted-foreground">
			{#if isRegistration}
				This will be the admin account for your Ghostwriter instance.
			{:else}
				Your session is stored locally in your browser.
			{/if}
		</p>
	</div>
</div>
