from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import base64


class ProductAPILogic(models.Model):
    _name = 'product.api.logic'
    _description = 'Helper model for product API logic'

    def create_or_update_product(self, data):
        """Creates or updates a product based on the provided data.

        Args:
            data (dict): The product data in JSON format.

        Returns:
            odoo.product.product: The created or updated product record.
        """

        try:
            # Main Product Data
            product_data = {
                'name': data.get('title'),
                'default_code': data.get('sku'),
                'list_price': float(data.get('price', 0.0)),  # Use list_price for sale price
                'weight': float(data.get('weight', 0.0)) if data.get('weight') else 0.0,
            }

            # Check if a product with the same external ID already exists
            existing_product = self.env['product.template'].search([('product_id', '=', data.get('product_id'))],
                                                                   limit=1)

            if existing_product:
                # Update the existing product
                existing_product.write(product_data)
                product = existing_product
            else:
                # Create a new product
                product_data['product_id'] = data.get('product_id')
                product = self.env['product.template'].create(product_data)

            # Handle Product Variants
            self._process_variants(product, data.get('variants', []))

            # Handle Images
            self._process_images(product, data.get('images', []))

            return product

        except Exception as e:
            raise UserError(_("Error creating/updating product: %s") % str(e))

    def _process_variants(self, product, variants_data):
        """Processes and creates/updates product variants.

        Args:
            product (odoo.product.template): The product template.
            variants_data (list): A list of variant data dictionaries.
        """
        if not variants_data:
            return

        for variant_data in variants_data:
            variant_values = {}
            variant_id = variant_data.get('id')
            variant_sku = variant_data.get('sku')
            variant_name = variant_data.get('name')
            variant_price = float(variant_data.get('price', 0.0))  # Use list_price

            # Find or create the product.product (product.variant) record
            existing_variant = self.env['product.product'].search(
                [('product_tmpl_id', '=', product.id), ('product_id', '=', variant_id)], limit=1)

            if existing_variant:
                # Update the existing variant
                variant_values.update({
                    'default_code': variant_sku,
                    'name': variant_name,
                    'list_price': variant_price,
                    'weight': float(variant_data.get('weight', 0.0)) if variant_data.get('weight') else 0.0,
                })
                existing_variant.write(variant_values)
                variant = existing_variant
            else:
                # Create new variant
                variant_values.update({
                    'product_tmpl_id': product.id,
                    'default_code': variant_sku,
                    'name': variant_name,
                    'list_price': variant_price,
                    'product_id': variant_id,
                    'weight': float(variant_data.get('weight', 0.0)) if variant_data.get('weight') else 0.0,
                })
                variant = self.env['product.product'].create(variant_values)

    def _process_images(self, product, images_data):
        """Processes and adds images to the product.

        Args:
            product (odoo.product.template): The product template.
            images_data (list): A list of image data dictionaries.
        """
        if not images_data:
            return

        for image_data in images_data:
            image_url = image_data.get('url')
            try:
                # Download the image
                response = requests.get(image_url, stream=True)
                response.raise_for_status()  # Raise an exception for bad status codes
                image_data = base64.b64encode(response.content)

                # Create the product image
                self.env['product.image'].create({
                    'name': product.name,
                    'product_tmpl_id': product.id,
                    'image_1920': image_data,
                })
            except requests.exceptions.RequestException as e:
                self.env['ir.logging'].sudo().create({
                    'name': 'Product Image API Error',
                    'type': 'server',
                    'level': 'ERROR',
                    'message': f"Failed to download image from {image_url}: {e}",
                    'dbname': self.env.cr.dbname,
                    'model': self._name,
                    'res_id': product.id,
                })

                raise UserError(_("Failed to download image from %s: %s" % (image_url, e)))
            except Exception as e:
                self.env['ir.logging'].sudo().create({
                    'name': 'Product Image API Error',
                    'type': 'server',
                    'level': 'ERROR',
                    'message': f"Failed to process image from {image_url}: {e}",
                    'dbname': self.env.cr.dbname,
                    'model': self._name,
                    'res_id': product.id,
                })
                raise UserError(_("Failed to process image from %s: %s" % (image_url, e)))