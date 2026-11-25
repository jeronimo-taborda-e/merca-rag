# Fotos del catálogo

Ponga aquí las fotos de los productos (JPG, PNG o WEBP), **una carpeta por producto base**.
El nombre de la carpeta enlaza la foto con su ficha de producto. Cada foto pertenece a **una sola** ficha (su único dueño en la base)
y el producto que muestra se obtiene a través de esa ficha:

```
data/imagenes/aguacate_hass/aguacate_1.jpg   ->  FICHA_AGUACATE_HASS  ->  producto "Aguacate Hass ..."
data/imagenes/cafe_molido_tostado/bolsa.png  ->  FICHA_CAFE_MOLIDO_TOSTADO
```

- Mínimo recomendado: 4 fotos en al menos 4 carpetas distintas (como en el laboratorio).
- Las fotos que NO deben estar en la base (para probar imagen -> imagen e imagen -> texto) van en `data/consultas/`.
- Opcional: `data/imagenes/manifest.csv` con columnas `archivo,codigo_doc,descripcion,etiquetas`
  (etiquetas separadas por `;`) para dar a cada foto otra ficha, una descripción corta (máx. 200 caracteres) o sus etiquetas.
- Una foto cuya carpeta no corresponde a ninguna ficha cargada no se inserta: la carga la reporta en `omitidas`.
- La misma foto con otro nombre no se duplica: se identifica por su SHA-256.

## Nombres de carpeta válidos

| Carpeta | Producto base |
|---|---|
| `aceite_de_girasol/` | Aceite de girasol |
| `agua_con_gas/` | Agua con gas |
| `agua_sin_gas/` | Agua sin gas |
| `aguacate_hass/` | Aguacate Hass |
| `alimento_seco_para_gato/` | Alimento seco para gato |
| `alimento_seco_para_perro_adulto/` | Alimento seco para perro adulto |
| `arena_para_gato/` | Arena para gato |
| `arepa_de_maiz_blanco/` | Arepa de maíz blanco |
| `arequipe/` | Arequipe |
| `aromatica_de_frutos_rojos/` | Aromática de frutos rojos |
| `arroz_blanco/` | Arroz blanco |
| `azucar_blanca/` | Azúcar blanca |
| `banano_criollo/` | Banano criollo |
| `bebida_hidratante/` | Bebida hidratante |
| `blanqueador/` | Blanqueador |
| `bolsas_de_basura/` | Bolsas de basura |
| `bombones_surtidos/` | Bombones surtidos |
| `cafe_en_grano_especial/` | Café en grano especial |
| `cafe_molido_tostado/` | Café molido tostado |
| `cafe_soluble/` | Café soluble |
| `carne_molida_de_res/` | Carne molida de res |
| `cebolla_cabezona_blanca/` | Cebolla cabezona blanca |
| `champu_anticaspa/` | Champú anticaspa |
| `chocolate_de_mesa/` | Chocolate de mesa |
| `chocolatina_con_leche/` | Chocolatina con leche |
| `chorizo_antioqueno/` | Chorizo antioqueño |
| `cocoa_en_polvo/` | Cocoa en polvo |
| `crema_dental/` | Crema dental |
| `crema_humectante_corporal/` | Crema humectante corporal |
| `croissant_mantequilla/` | Croissant mantequilla |
| `desodorante_en_barra/` | Desodorante en barra |
| `detergente_en_polvo/` | Detergente en polvo |
| `detergente_liquido/` | Detergente líquido |
| `filete_de_tilapia/` | Filete de tilapia |
| `frijol_cargamanto/` | Fríjol cargamanto |
| `galletas_con_chips_de_chocolate/` | Galletas con chips de chocolate |
| `galletas_de_soda/` | Galletas de soda |
| `gaseosa_cola/` | Gaseosa cola |
| `harina_de_maiz_precocida/` | Harina de maíz precocida |
| `helado_de_vainilla/` | Helado de vainilla |
| `huevos_aa_rojos/` | Huevos AA rojos |
| `jabon_de_bano_antibacterial/` | Jabón de baño antibacterial |
| `jamon_de_cerdo/` | Jamón de cerdo |
| `jugo_de_mango/` | Jugo de mango |
| `kumis/` | Kumis |
| `lavaloza_en_crema/` | Lavaloza en crema |
| `leche_deslactosada/` | Leche deslactosada |
| `leche_entera/` | Leche entera |
| `lechuga_crespa/` | Lechuga crespa |
| `lentejas/` | Lentejas |
| `limpiapisos_lavanda/` | Limpiapisos lavanda |
| `lomo_de_cerdo/` | Lomo de cerdo |
| `lulo/` | Lulo |
| `malta/` | Malta |
| `mani_salado/` | Maní salado |
| `mantequilla_con_sal/` | Mantequilla con sal |
| `mora_de_castilla/` | Mora de Castilla |
| `nuggets_de_pollo/` | Nuggets de pollo |
| `pan_de_bono/` | Pan de bono |
| `pan_integral/` | Pan integral |
| `pan_tajado_blanco/` | Pan tajado blanco |
| `panela/` | Panela |
| `papa_pastusa/` | Papa pastusa |
| `papas_a_la_francesa_congeladas/` | Papas a la francesa congeladas |
| `papas_fritas_de_limon/` | Papas fritas de limón |
| `papel_higienico_doble_hoja/` | Papel higiénico doble hoja |
| `pasta_spaghetti/` | Pasta spaghetti |
| `pechuga_de_pollo/` | Pechuga de pollo |
| `ponque_de_vainilla/` | Ponqué de vainilla |
| `pulpa_de_fruta_maracuya/` | Pulpa de fruta maracuyá |
| `queso_campesino/` | Queso campesino |
| `sal_refinada_yodada/` | Sal refinada yodada |
| `salchicha_tipo_ranchera/` | Salchicha tipo ranchera |
| `snack_dental_para_perro/` | Snack dental para perro |
| `te_helado_de_limon/` | Té helado de limón |
| `toallas_higienicas/` | Toallas higiénicas |
| `tomate_chonto/` | Tomate chonto |
| `tostadas_de_pan/` | Tostadas de pan |
| `verduras_mixtas_congeladas/` | Verduras mixtas congeladas |
| `yogur_de_fresa/` | Yogur de fresa |
| `zanahoria/` | Zanahoria |
