using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Verse;

namespace AiRim
{
    /// <summary>
    /// Owns the socket to the orchestrator on a background thread. The main thread only ever
    /// calls Send(string); it never blocks on the network.
    /// </summary>
    public static class Transport
    {
        private const int MaxQueue = 5000;
        private static readonly ConcurrentQueue<string> queue = new ConcurrentQueue<string>();
        private static readonly AutoResetEvent signal = new AutoResetEvent(false);
        private static Thread thread;
        private static volatile bool running;
        private static int dropped;
        private static int queued;

        public static volatile bool Connected;

        public static void Start()
        {
            if (thread != null) return;
            running = true;
            thread = new Thread(Loop) { IsBackground = true, Name = "AiRim.Transport" };
            thread.Start();
        }

        public static void Stop()
        {
            running = false;
            signal.Set();
        }

        public static void Send(string line)
        {
            if (queued >= MaxQueue)
            {
                Interlocked.Increment(ref dropped);
                return;
            }
            queue.Enqueue(line);
            Interlocked.Increment(ref queued);
            signal.Set();
        }

        /// <summary>Called from the main thread; reports and resets the drop counter.</summary>
        public static int TakeDropped() => Interlocked.Exchange(ref dropped, 0);

        private static void Loop()
        {
            int backoffMs = 1000;
            while (running)
            {
                TcpClient client = null;
                try
                {
                    client = new TcpClient();
                    client.NoDelay = true;
                    client.Connect(AiRimMod.Settings.host, AiRimMod.Settings.port);
                    Connected = true;
                    backoffMs = 1000;
                    Log.Message($"[AiRim] connected to {AiRimMod.Settings.host}:{AiRimMod.Settings.port}");
                    using (var stream = client.GetStream())
                    using (var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = false })
                    {
                        while (running)
                        {
                            bool any = false;
                            while (queue.TryDequeue(out var line))
                            {
                                Interlocked.Decrement(ref queued);
                                writer.Write(line);
                                writer.Write('\n');
                                any = true;
                            }
                            if (any) writer.Flush();
                            signal.WaitOne(500);
                        }
                    }
                }
                catch (Exception e)
                {
                    if (Connected) Log.Warning($"[AiRim] connection lost: {e.Message}");
                }
                finally
                {
                    Connected = false;
                    try { client?.Close(); } catch { /* ignore */ }
                }
                if (!running) break;
                Thread.Sleep(backoffMs);
                backoffMs = Math.Min(backoffMs * 2, 15000);
            }
        }
    }
}
