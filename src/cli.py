"""OrgBridge AI - FalkorDB Interactive CLI & REPL.

Provides an easy-to-use Cypher shell for querying finpay_graph, vaultly_graph,
and merged_brain, viewing schemas, and running M&A graph operations.
"""

import sys
import argparse
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import settings
from src.db.client import db_client
from src.schema.cypher_schema import sanitize_cypher_query
from src.data.seed import seed_all_graphs

console = Console()


def display_query_result(result, query: str, graph_name: str):
    """Renders Cypher query results as a formatted Rich table."""
    if not hasattr(result, "result_set") or not result.result_set:
        console.print(f"[yellow]Query executed on [{graph_name}]. No rows returned.[/yellow]")
        if hasattr(result, "statistics"):
            console.print(f"[dim]{result.statistics}[/dim]")
        return

    # Extract headers
    headers = [str(header) if not isinstance(header, list) else str(header[0]) for header in result.header] if hasattr(result, "header") else [f"col_{i}" for i in range(len(result.result_set[0]))]

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
        sanitized = sanitize_cypher_query(query)
        res = db_client.query(graph_name, sanitized, sanitize=False)
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

    args = parser.parse_args()

    if args.subcommand == "query":
        run_query(args.graph, args.cypher)
    elif args.subcommand == "list-graphs":
        list_graphs()
    else:
        interactive_repl(getattr(args, "graph", settings.graph_merged))


if __name__ == "__main__":
    main()
