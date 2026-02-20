<script lang="ts">
	const mediaPageModule = import('$lib/components/features/media/MediaPage.svelte');
</script>

{#await mediaPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading media…</div>
{:then module}
	{@const MediaPage = module.default}
	<MediaPage />
{/await}
