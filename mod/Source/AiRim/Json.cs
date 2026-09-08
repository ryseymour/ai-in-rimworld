using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace AiRim
{
    /// <summary>Minimal JSON writer. Avoids a Newtonsoft dependency and its Mono version conflicts.</summary>
    public sealed class Json
    {
        private readonly StringBuilder sb = new StringBuilder(256);
        private bool first = true;

        public static Json Obj() => new Json().Begin();

        private Json Begin() { sb.Append('{'); return this; }

        private void Key(string k)
        {
            if (!first) sb.Append(',');
            first = false;
            Str(k);
            sb.Append(':');
        }

        public Json Put(string k, string v) { Key(k); if (v == null) sb.Append("null"); else Str(v); return this; }
        public Json Put(string k, int v) { Key(k); sb.Append(v.ToString(CultureInfo.InvariantCulture)); return this; }
        public Json Put(string k, long v) { Key(k); sb.Append(v.ToString(CultureInfo.InvariantCulture)); return this; }
        public Json Put(string k, bool v) { Key(k); sb.Append(v ? "true" : "false"); return this; }
        public Json Put(string k, float v) { Key(k); sb.Append(float.IsNaN(v) || float.IsInfinity(v) ? "null" : v.ToString("0.###", CultureInfo.InvariantCulture)); return this; }
        public Json PutRaw(string k, string rawJson) { Key(k); sb.Append(rawJson ?? "null"); return this; }
        public Json Put(string k, Json nested) { Key(k); sb.Append(nested.ToString()); return this; }

        public Json PutInts(string k, int a, int b, int c)
        {
            Key(k);
            sb.Append('[').Append(a).Append(',').Append(b).Append(',').Append(c).Append(']');
            return this;
        }

        public Json PutStrings(string k, IEnumerable<string> items)
        {
            Key(k);
            sb.Append('[');
            bool f = true;
            foreach (var s in items) { if (!f) sb.Append(','); f = false; Str(s); }
            sb.Append(']');
            return this;
        }

        public Json PutObjects(string k, IEnumerable<Json> items)
        {
            Key(k);
            sb.Append('[');
            bool f = true;
            foreach (var j in items) { if (!f) sb.Append(','); f = false; sb.Append(j.ToString()); }
            sb.Append(']');
            return this;
        }

        private void Str(string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        public override string ToString() => sb.ToString() + "}";
    }
}
