<script lang="ts">
	const readerPageModule = import('$lib/components/features/reader/ReaderPage.svelte');
</script>

{#await readerPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading reader…</div>
{:then module}
	{@const ReaderPage = module.default}
	<ReaderPage />
{/await}
