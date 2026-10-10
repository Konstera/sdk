namespace Konstera.Sdk.Internal;

/// <summary>
/// Per-invocation ambient context — carries the current invocation id
/// through <c>agent.HandleAsync</c> without forcing the agent to thread
/// it through every service call.
///
/// The SDK runtime sets this before dispatching to <c>HandleAsync</c> and
/// resets it after; <see cref="Services.LogService"/> and
/// <see cref="Services.LlmService"/> read it lazily.
///
/// Uses <see cref="AsyncLocal{T}"/> so it survives every <c>await</c> and
/// is inherited by child tasks — mirrors the Python SDK's
/// <c>contextvars.ContextVar</c> equivalent and the kernel's
/// <c>AmbientTenantScope</c> pattern.
/// </summary>
public static class InvocationContext
{
    private static readonly AsyncLocal<string?> _current = new();

    public static string? Current => _current.Value;

    public static IDisposable Enter(string invocationId)
    {
        var previous = _current.Value;
        _current.Value = invocationId;
        return new Popper(previous);
    }

    private sealed class Popper : IDisposable
    {
        private readonly string? _previous;
        private int _disposed;

        internal Popper(string? previous) { _previous = previous; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) == 0)
            {
                _current.Value = _previous;
            }
        }
    }
}
