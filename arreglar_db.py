import sqlite3
# Conectamos a tu base de datos
conn = sqlite3.connect('pizzatrack_v4.db')
# Este es el comando mágico que cambia el estado
conn.execute("UPDATE pedidos SET estado = 'Entregado' WHERE id = 13")
conn.commit()
conn.close()
print("¡Estado cambiado a LISTO en la base de datos!")