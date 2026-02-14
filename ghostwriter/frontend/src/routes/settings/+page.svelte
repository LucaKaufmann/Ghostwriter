<script lang="ts">
	const settingsPageModule = import('$lib/components/features/settings/SettingsPage.svelte');
</script>

{#await settingsPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading settings…</div>
{:then module}
	{@const SettingsPage = module.default}
	<SettingsPage />
{/await}
