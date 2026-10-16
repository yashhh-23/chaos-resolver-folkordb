"""OrgBridge AI - FalkorDB Interactive CLI & REPL.

Provides an easy-to-use Cypher shell for querying finpay_graph, vaultly_graph,
and merged_brain, viewing schemas, and running M&A graph operations.
"""

import argparse
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import settings
from src.db.client import db_client
from src.data.seed import seed_all_graphs

console = Console()


def display_query_result(result, query: str, graph_name: str):
    """Renders Cypher query results as a formatted Rich table."""
    if not hasattr(result, "result_set") or not result.result_set:
        console.print(f"[yellow]Query executed on [{graph_name}]. No rows returned.[/yellow]")
        if hasattr(result, "statistics"):
            console.print(f"[dim]{result.statistics}[/dim]")
        return

    # Extract headers (FalkorDB returns [[type_id, 'col_name'], ...])
    headers = []
    if hasattr(result, "header") and result.header:
        for h in result.header:
            if isinstance(h, (list, tuple)) and len(h) > 1:
                headers.append(str(h[1]))
            elif isinstance(h, (list, tuple)) and len(h) == 1:
                headers.append(str(h[0]))
            else:
                headers.append(str(h))
    else:
        headers = [f"col_{i}" for i in range(len(result.result_set[0]))]


    table = Table(title=f"Graph: {graph_name} | Query: {query[:60]}...", show_lines=True)
    for h in headers:
        table.add_column(str(h), style="cyan", overflow="fold")

    for row in result.result_set:
        formatted_row = []
        for cell in row:
            if hasattr(cell, "properties"):
                props = ", ".join(f"{k}: {v}" for k, v in cell.properties.items())
                formatted_row.append(f"({':'.join(cell.labels or [])}) {{{props}}}")
            elif hasattr(cell, "relation"):
                formatted_row.append(f"[:{cell.relation}]")
            else:
                formatted_row.append(str(cell))
        table.add_row(*formatted_row)

    console.print(table)
    if hasattr(result, "statistics"):
        console.print(f"[dim]Stats: {result.statistics}[/dim]")


def run_query(graph_name: str, query: str):
    """Executes a single query and prints formatted results."""
    try:
        res = db_client.query(graph_name, query, sanitize=True)
        display_query_result(res, query, graph_name)
    except Exception as e:
        console.print(f"[bold red]Query Error:[/bold red] {e}")


def list_graphs():
    """Lists all available graphs in FalkorDB."""
    try:
        db = db_client.connect()
        graphs = db.list_graphs()
        table = Table(title="FalkorDB Active Graphs", show_lines=True)
        table.add_column("Graph Name", style="green")
        for g in graphs:
            table.add_row(str(g))
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error connecting to FalkorDB:[/bold red] {e}")


def interactive_repl(initial_graph: Optional[str] = None):
    """Launches an interactive Cypher shell for FalkorDB."""
    current_graph = initial_graph or settings.graph_merged
    console.print(
        Panel.fit(
            f"[bold cyan]OrgBridge AI - FalkorDB Shell[/bold cyan]\n"
            f"Active Graph: [bold green]{current_graph}[/bold green]\n\n"
            f"Commands:\n"
            f"  [yellow]use <graph>[/yellow]   Switch active graph ({settings.graph_finpay}, {settings.graph_vaultly}, {settings.graph_merged})\n"
            f"  [yellow]graphs[/yellow]        List all graphs\n"
            f"  [yellow]seed[/yellow]          Run Phase 1 seeder\n"
            f"  [yellow]auto-link[/yellow]     Run Phase 2 M&A Auto-Linker Engine\n"
            f"  [yellow]exit[/yellow] / [yellow]quit[/yellow]    Exit shell\n"
            f"  Or enter any Cypher query directly (e.g. [green]MATCH (n) RETURN count(n)[/green])",
            title="FalkorDB REPL",
            border_style="cyan",
        )
    )

    try:
        db_client.connect()
    except Exception as e:
        console.print(f"[bold red]Warning:[/bold red] Could not connect to FalkorDB: {e}")
        console.print("Make sure Docker or FalkorDB Cloud is reachable before executing queries.\n")

    while True:
        try:
            line = input(f"falkordb ({current_graph})> ").strip()
            if not line:
                continue

            lower = line.lower()
            if lower in ["exit", "quit", "q"]:
                console.print("[dim]Goodbye![/dim]")
                break
            elif lower == "graphs":
                list_graphs()
            elif lower.startswith("use "):
                parts = line.split(maxsplit=1)
                if len(parts) > 1:
                    current_graph = parts[1].strip()
                    console.print(f"[green]Switched active graph to:[/green] [bold]{current_graph}[/bold]")
            elif lower == "seed":
                console.print("[cyan]Seeding all graphs...[/cyan]")
                seed_all_graphs(clear_first=False)
            elif lower in ["auto-link", "autolink"]:
                from src.pipeline.auto_linker import auto_linker_engine
                console.print(f"[cyan]Running Auto-Linker Engine on '{current_graph}'...[/cyan]")
                auto_linker_engine.run_pipeline(current_graph)
            else:
                run_query(current_graph, line)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break


def main():
    parser = argparse.ArgumentParser(description="OrgBridge AI FalkorDB CLI")
    subparsers = parser.add_subparsers(dest="subcommand")

    # repl subcommand
    repl_parser = subparsers.add_parser("repl", help="Start interactive Cypher REPL")
    repl_parser.add_argument("--graph", default=settings.graph_merged, help="Initial graph to select")

    # query subcommand
    query_parser = subparsers.add_parser("query", help="Execute a Cypher query")
    query_parser.add_argument("cypher", help="Cypher query string")
    query_parser.add_argument("--graph", default=settings.graph_merged, help="Target graph")

    # list-graphs subcommand
    subparsers.add_parser("list-graphs", help="List all graphs in FalkorDB")

    # auto-link subcommand
    link_parser = subparsers.add_parser("auto-link", help="Execute M&A Auto-Linker Engine")
    link_parser.add_argument("--graph", default=settings.graph_merged, help="Target graph to link")
    link_parser.add_argument("--threshold", type=float, default=0.82, help="Similarity threshold (default 0.82)")

    # serve subcommand
    serve_parser = subparsers.add_parser("serve", help="Start FastAPI REST backend server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default 8000)")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host interface (default 0.0.0.0)")

    # tool subcommand
    tool_parser = subparsers.add_parser("tool", help="Run one of the 5 deterministic M&A agent tools")
    tool_sub = tool_parser.add_subparsers(dest="tool_action")

    # tool: find-expert
    t_exp = tool_sub.add_parser("find-expert", help="Find subject-matter expert counterpart")
    t_exp.add_argument("--topic", required=True, help="Topic/domain to search")
    t_exp.add_argument("--company", default="Vaultly", help="Target company")

    # tool: conflicts
    t_conf = tool_sub.add_parser("conflicts", help="Detect policy & compliance conflicts")
    t_conf.add_argument("--domain", default=None, help="Optional domain filter")

    # tool: redundant
    tool_sub.add_parser("redundant", help="Find redundant systems clusters")

    # tool: lineage
    t_lin = tool_sub.add_parser("lineage", help="Trace system decision and documentation lineage")
    t_lin.add_argument("--system", required=True, help="System name to trace")

    # tool: warm-intro
    t_intro = tool_sub.add_parser("warm-intro", help="Find shortest warm introduction path between two people")
    t_intro.add_argument("--person-a", required=True, help="Person A name")
    t_intro.add_argument("--person-b", required=True, help="Person B name")

    # mutate subcommand (Phase 5 Live Brain Mutations)
    mutate_parser = subparsers.add_parser("mutate", help="Execute live graph mutations (Track 03)")
    mutate_sub = mutate_parser.add_subparsers(dest="mutate_action")
    mutate_sub.add_parser("resolve-auth", help="Resolve authentication session policy conflict")
    mutate_sub.add_parser("resolve-retention", help="Resolve data retention compliance conflict")
    mutate_sub.add_parser("merge-teams", help="Merge FinPay SecArch and Vaultly Identity teams")
    mutate_sub.add_parser("reset-demo", help="Reset FalkorDB multigraphs to pristine initial state")

    args = parser.parse_args()

    if args.subcommand == "query":
        run_query(args.graph, args.cypher)
    elif args.subcommand == "list-graphs":
        list_graphs()
    elif args.subcommand == "auto-link":
        from src.pipeline.auto_linker import AutoLinkerEngine
        engine = AutoLinkerEngine(threshold=args.threshold)
        engine.run_pipeline(args.graph)
    elif args.subcommand == "serve":
        import uvicorn
        console.print(f"[bold green]Starting OrgBridge AI API Server on http://{args.host}:{args.port}[/bold green]")
        uvicorn.run("src.api.main:app", host=args.host, port=args.port, reload=True)
    elif args.subcommand == "tool":
        from src.tools.graph_tools import agent_tools
        if args.tool_action == "find-expert":
            res = agent_tools.find_counterpart_expert(topic=args.topic, company=args.company)
            console.print(Panel(res.text_answer, title="Tool: find_counterpart_expert", border_style="green"))
        elif args.tool_action == "conflicts":
            res = agent_tools.detect_policy_conflicts(domain=args.domain)
            console.print(Panel(res.text_answer, title="Tool: detect_policy_conflicts", border_style="yellow"))
        elif args.tool_action == "redundant":
            res = agent_tools.find_redundant_systems()
            console.print(Panel(res.text_answer, title="Tool: find_redundant_systems", border_style="cyan"))
        elif args.tool_action == "lineage":
            res = agent_tools.trace_decision_lineage(system_name=args.system)
            console.print(Panel(res.text_answer, title="Tool: trace_decision_lineage", border_style="magenta"))
        elif args.tool_action == "warm-intro":
            res = agent_tools.get_warm_intro_path(person_a=args.person_a, person_b=args.person_b)
            console.print(Panel(res.text_answer, title="Tool: get_warm_intro_path", border_style="blue"))
        else:
            tool_parser.print_help()
    elif args.subcommand == "mutate":
        from src.pipeline.mutations import live_mutations
        if args.mutate_action == "resolve-auth":
            res = live_mutations.resolve_auth_conflict()
            console.print(Panel(f"[green]Status: {res['status']}[/green]\n[bold]{res['resolution_summary']}[/bold]", title="Live Mutation: Resolve Auth Conflict", border_style="green"))
        elif args.mutate_action == "resolve-retention":
            res = live_mutations.resolve_retention_conflict()
            console.print(Panel(f"[green]Status: {res['status']}[/green]\n[bold]{res['resolution_summary']}[/bold]", title="Live Mutation: Resolve Retention Conflict", border_style="green"))
        elif args.mutate_action == "merge-teams":
            res = live_mutations.merge_teams()
            console.print(Panel(f"[green]Status: {res['status']}[/green]\n[bold]{res['resolution_summary']}[/bold]", title="Live Mutation: Merge Teams", border_style="green"))
        elif args.mutate_action == "reset-demo":
            from src.pipeline.mutations import live_mutations
            console.print("[cyan]Resetting demo multigraphs in FalkorDB...[/cyan]")
            res = live_mutations.reset_demo(include_subgraph=False)
            console.print(f"[bold green]{res['message']}[/bold green]")
        else:
            mutate_parser.print_help()
    else:
        interactive_repl(getattr(args, "graph", settings.graph_merged))


if __name__ == "__main__":
    main()

